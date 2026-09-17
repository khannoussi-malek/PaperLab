"""A library paper's references and citing works: fetched once, stored, ranked for this library (M7.5).

- Semantic Scholar answers both directions; OpenAlex is merged in when it's ticked (D77). Stored in `external_refs`
  and `paper_references`, so ranking can count how many library papers share a reference (D78).
- Ranking is tiers (D80): co-citation inside the library, closeness to the reader's notes, a free PDF, citation count.
- Importing downloads a free PDF exactly as Find papers' Add does (D84); nothing is fetched for the new paper (P5).
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import discovery, papers
from app.core.candidates import Candidate, from_s2, from_work, merge, ordered_pdf_urls
from app.core.errors import Conflict
from app.models import ExternalRef, Note, NoteEmbedding, Paper, paper_references
from app.providers import embedding, openalex, semantic_scholar

logger = logging.getLogger(__name__)

REFS_CAP = 500
CITING_CAP = 200
CO_CITATION_SUMMARY = 3
# A fetch the worker never finished (a restart mid-job) can be asked for again after this long.
FETCH_STALE = timedelta(minutes=10)

FETCH_FAILED = "Fetching references failed. Try again."
REFERENCES_OFF = "Semantic Scholar is off. Turn it on in Settings → Paper sources to see references."
REFERENCES_UNKNOWN = "Semantic Scholar doesn't know this paper, so it can't list its references."


@dataclass(frozen=True)
class ReferenceRow:
    id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    s2_id: str | None
    cited_by_count: int | None
    has_pdf: bool
    cocitation: int  # library papers citing it (or, for citing works, library papers it cites)
    paper_id: uuid.UUID | None  # set when the library holds it
    position: int


@dataclass(frozen=True)
class Summary:
    cited_by_3plus: int
    with_pdf: int


@dataclass(frozen=True)
class Listing:
    state: str
    error: str | None
    direction: str
    summary: Summary
    rows: list[ReferenceRow]


# --- fetch -------------------------------------------------------------------------------------------------------


async def _from_semantic_scholar(providers: discovery.Providers, paper: Paper) -> dict[str, list[Candidate]] | None:
    """None when Semantic Scholar doesn't know the paper."""
    key = await discovery.s2_key(providers.s2, paper)
    if key is None:
        return None
    cites = await semantic_scholar.references(providers.s2, key, REFS_CAP)
    if cites is None:
        return None
    cited_by = await semantic_scholar.citations(providers.s2, key, CITING_CAP) or []
    return {"cites": [from_s2(p) for p in cites], "cited_by": [from_s2(p) for p in cited_by]}


async def _from_openalex(providers: discovery.Providers, paper: Paper) -> dict[str, list[Candidate]]:
    ids = await openalex.referenced_works(providers.openalex, paper.openalex_id)
    cites = await openalex.works_by_ids(providers.openalex, ids[:REFS_CAP])
    cited_by = await openalex.citing_works(providers.openalex, paper.openalex_id, CITING_CAP)
    return {"cites": [from_work(w) for w in cites], "cited_by": [from_work(w) for w in cited_by]}


async def fetch(session: AsyncSession, providers: discovery.Providers, paper: Paper) -> list[str]:
    """Stores both directions for `paper` and returns a notice per source that failed. Raises Conflict when no
    source could answer: none is on, the sources don't know the paper, or every one failed."""
    found: dict[str, dict[str, list[Candidate]]] = {}  # source -> direction -> candidates, most trusted first
    notices: list[str] = []
    unknown = False
    asks = []
    if providers.openalex is not None and paper.openalex_id:
        asks.append(("openalex", _from_openalex))
    if providers.s2 is not None:
        asks.append(("semantic_scholar", _from_semantic_scholar))
    if not asks:
        raise Conflict(REFERENCES_OFF)
    for source, ask in asks:
        try:
            answer = await ask(providers, paper)
        except httpx.HTTPError as exc:
            logger.info("%s failed for the references of %s: %s", source, paper.id, exc)
            notices.append(discovery.notice(source, exc))
            continue
        if answer is None:
            unknown = True
        else:
            found[source] = answer
    if not found:
        raise Conflict(" ".join(notices) if notices else REFERENCES_UNKNOWN if unknown else FETCH_FAILED)
    for direction, cap in (("cites", REFS_CAP), ("cited_by", CITING_CAP)):
        merged = merge({source: lists[direction] for source, lists in found.items()}, cap)
        if direction == "cited_by":  # newest first, as the reverse direction is read (addendum §3d)
            merged = sorted(merged, key=lambda c: -(c.year or 0))
        ids = [await _upsert(session, candidate) for candidate in merged]
        await session.execute(
            delete(paper_references).where(
                paper_references.c.paper_id == paper.id, paper_references.c.direction == direction
            )
        )
        rows = [
            {"paper_id": paper.id, "ref_id": ref_id, "direction": direction, "position": position}
            for position, ref_id in enumerate(dict.fromkeys(ids))
        ]
        if rows:
            await session.execute(insert(paper_references), rows)
    await session.commit()
    return notices


async def _upsert(session: AsyncSession, candidate: Candidate) -> uuid.UUID:
    """The stored reference for `candidate`, created or refreshed. Rows that turn out to be the same paper (one known
    by its Semantic Scholar id, another by its DOI) fold into the oldest, and an imported row always wins."""
    matches = _same_reference(candidate.s2_id, candidate.openalex_id, candidate.doi, candidate.arxiv_id)
    existing = list(
        await session.scalars(
            select(ExternalRef)
            .where(or_(*matches))
            .order_by(ExternalRef.imported_as.is_(None), ExternalRef.fetched_at, ExternalRef.id)
        )
    )
    fields = {
        "title": candidate.title,
        "authors": candidate.authors,
        "year": candidate.year,
        "venue": candidate.venue,
        "cited_by_count": candidate.cited_by_count,
    }
    ids = {"s2_id": candidate.s2_id, "openalex_id": candidate.openalex_id, "doi": candidate.doi,
           "arxiv_id": candidate.arxiv_id}  # fmt: skip
    if not existing:
        return await session.scalar(
            insert(ExternalRef).values(**fields, pdf_urls=candidate.pdf_urls, **ids).returning(ExternalRef.id)
        )
    keeper, *duplicates = existing
    for duplicate in duplicates:
        for name in ids:
            ids[name] = ids[name] or getattr(duplicate, name)
        await _repoint(session, duplicate.id, keeper.id)
        await session.delete(duplicate)
    await session.flush()
    for name, value in ids.items():
        ids[name] = value or getattr(keeper, name)
    if candidate.title != keeper.title:  # a new title needs a new vector
        fields |= {"title_embedding": None, "title_embed_model": None}
    # Preserve PDF URLs from candidate, duplicates, and keeper when folding
    fields["pdf_urls"] = ordered_pdf_urls(
        ids["arxiv_id"],
        *candidate.pdf_urls,
        *(url for row in [*duplicates, keeper] for url in row.pdf_urls),
    )
    await session.execute(update(ExternalRef).where(ExternalRef.id == keeper.id).values(**fields, **ids))
    return keeper.id


def _same_reference(s2_id: str | None, openalex_id: str | None, doi: str | None, arxiv_id: str | None) -> list:
    """Conditions matching any stored reference that shares an id. Every candidate has at least one id: Semantic
    Scholar records carry a paperId and OpenAlex records a work id."""
    conditions = []
    if s2_id:
        conditions.append(ExternalRef.s2_id == s2_id)
    if openalex_id:
        conditions.append(ExternalRef.openalex_id == openalex_id)
    if doi:
        conditions.append(func.lower(ExternalRef.doi) == doi.lower())
    if arxiv_id:
        conditions.append(ExternalRef.arxiv_id == arxiv_id)
    return conditions


async def _repoint(session: AsyncSession, old: uuid.UUID, new: uuid.UUID) -> None:
    """Moves every paper's link from a duplicate reference to the row it folds into, keeping the first position."""
    await session.execute(
        text(
            "INSERT INTO paper_references (paper_id, ref_id, direction, position) "
            "SELECT paper_id, :new, direction, position FROM paper_references WHERE ref_id = :old "
            "ON CONFLICT DO NOTHING"
        ),
        {"old": old, "new": new},
    )
    await session.execute(delete(paper_references).where(paper_references.c.ref_id == old))


async def request_fetch(session: AsyncSession, paper_id: uuid.UUID) -> bool:
    """Marks the paper's references as fetching and returns whether a job should be queued: False while a recent
    fetch is still running, so a second click queues nothing."""
    await papers.get_paper(session, paper_id)
    stale = datetime.now(timezone.utc) - FETCH_STALE
    claimed = await session.scalar(
        update(Paper)
        .where(
            Paper.id == paper_id,
            or_(
                Paper.references_state != "fetching",
                Paper.references_requested_at.is_(None),
                Paper.references_requested_at < stale,
            ),
        )
        .values(references_state="fetching", references_error=None, references_requested_at=func.now())
        .returning(Paper.id)
    )
    await session.commit()
    return claimed is not None


async def set_state(session: AsyncSession, paper_id: uuid.UUID, state: str, error: str | None = None) -> None:
    await session.execute(
        update(Paper).where(Paper.id == paper_id).values(references_state=state, references_error=error)
    )
    await session.commit()


# --- embeddings --------------------------------------------------------------------------------------------------


async def embed_new(session: AsyncSession, embedder) -> None:
    """Vectors for reference titles and notes that have none, or were made by another model or before an edit."""
    model_name = settings.embed_model
    refs = (
        await session.execute(
            select(ExternalRef.id, ExternalRef.title).where(
                or_(ExternalRef.title_embedding.is_(None), ExternalRef.title_embed_model != model_name)
            )
        )
    ).all()
    if refs:
        vectors = await embedding.embed_documents(embedder, [title for _, title in refs])
        for (ref_id, _), vector in zip(refs, vectors):
            await session.execute(
                update(ExternalRef)
                .where(ExternalRef.id == ref_id)
                .values(title_embedding=vector, title_embed_model=model_name)
            )
    # ponytail: every fetch re-checks every note; with thousands of notes, embed on note save instead.
    notes = (
        await session.execute(
            select(Note.id, Note.body, Note.updated_at)
            .outerjoin(NoteEmbedding, NoteEmbedding.note_id == Note.id)
            .where(
                or_(
                    NoteEmbedding.note_id.is_(None),
                    NoteEmbedding.noted_at < Note.updated_at,
                    NoteEmbedding.embed_model != model_name,
                )
            )
        )
    ).all()
    if notes:
        vectors = await embedding.embed_documents(embedder, [body for _, body, _ in notes])
        for (note_id, _, updated_at), vector in zip(notes, vectors):
            await session.merge(
                NoteEmbedding(note_id=note_id, embedding=vector, embed_model=model_name, noted_at=updated_at)
            )
    await session.commit()


# --- listing -----------------------------------------------------------------------------------------------------

# ponytail: no vector index; at library scale (hundreds of refs, tens of notes) a scan beats an HNSW build. Add one
# when a library passes ~50k references.
_LISTING = text(
    """
    SELECT r.id, r.title, r.authors, r.year, r.venue, r.doi, r.arxiv_id, r.openalex_id, r.s2_id, r.cited_by_count,
           jsonb_array_length(r.pdf_urls) > 0 AS has_pdf,
           (SELECT count(DISTINCT other.paper_id) FROM paper_references other
             WHERE other.ref_id = r.id AND other.direction = pr.direction) AS cocitation,
           (SELECT max(1 - (r.title_embedding <=> n.embedding)) FROM note_embeddings n
             WHERE n.embed_model = r.title_embed_model) AS note_similarity,
           coalesce(r.imported_as, (
             SELECT p.id FROM papers p
              WHERE p.openalex_id = r.openalex_id
                 OR lower(p.doi) = lower(r.doi)
                 OR lower(p.doi) = '10.48550/arxiv.' || r.arxiv_id
              LIMIT 1)) AS paper_id,
           pr.position
      FROM paper_references pr
      JOIN external_refs r ON r.id = pr.ref_id
     WHERE pr.paper_id = :paper_id AND pr.direction = :direction
     ORDER BY cocitation DESC, note_similarity DESC NULLS LAST, has_pdf DESC, r.cited_by_count DESC NULLS LAST,
              pr.position
    """
)


async def listing(session: AsyncSession, paper_id: uuid.UUID, direction: str) -> Listing:
    paper = await papers.get_paper(session, paper_id)
    rows = [
        ReferenceRow(**{key: value for key, value in row._mapping.items() if key != "note_similarity"})
        for row in await session.execute(_LISTING, {"paper_id": paper_id, "direction": direction})
    ]
    return Listing(
        state=paper.references_state,
        error=paper.references_error,
        direction=direction,
        summary=summarize(rows),
        rows=rows,
    )


def summarize(rows: Sequence[ReferenceRow]) -> Summary:
    return Summary(
        cited_by_3plus=sum(row.cocitation >= CO_CITATION_SUMMARY for row in rows),
        with_pdf=sum(row.has_pdf for row in rows),
    )
