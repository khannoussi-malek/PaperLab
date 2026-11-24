"""A library paper's references and citing works: fetched once, stored, ranked for this library (M7.5).

- Semantic Scholar answers both directions; OpenAlex is merged in when it's ticked (D77). Stored in `external_refs`
  and `paper_references`, so ranking can count how many library papers share a reference (D78).
- Ranking is tiers (D80): co-citation inside the library, closeness to the reader's notes, a free PDF, citation count.
  A reference is in the library by `IN_LIBRARY`, the one match the tab, the References page and the graph share.
- Importing downloads a free PDF exactly as Find papers' Add does (D84); nothing is fetched for the new paper (P5).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import delete, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers import papers
from app.core.search import discovery, free_copy, source_clients
from app.core.search.candidates import merge, ordered_pdf_urls
from app.core.search.from_indexes import from_s2, from_work
from app.domain.candidates import Candidate
from app.domain.errors import Conflict, NotFound
from app.models import ExternalRef, Paper, paper_references
from app.providers import openalex, semantic_scholar

logger = logging.getLogger(__name__)

REFS_CAP = 500
CITING_CAP = 200
CO_CITATION_SUMMARY = 3
COCITED_MIN = 2  # D166, D177: the References page's threshold for both directions
# A fetch the worker never finished (a restart mid-job) can be asked for again after this long.
FETCH_STALE = timedelta(minutes=10)

FETCH_FAILED = "Fetching references failed. Try again."
REFERENCES_OFF = "Semantic Scholar is off. Turn it on in Settings → Paper sources to see references."
REFERENCES_UNKNOWN = "Semantic Scholar doesn't know this paper, so it can't list its references."
# Two papers' fetches can store the same new reference, or embed the same notes, at once: a unique violation or a
# deadlock fails one of them. Storing and embedding take this transaction-scoped advisory lock first.
# ponytail: one references write at a time across the library; per-reference locks if that ever matters.
REFERENCES_LOCK = 7_500_001
_TAKE_LOCK = text("SELECT pg_advisory_xact_lock(:key)")


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
    paper_has_pdf: bool | None  # whether that library paper has its PDF; None when the library doesn't hold it
    position: int
    queued_at: datetime | None  # when the reader marked it To read (D164)


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


async def _from_semantic_scholar(
    providers: source_clients.Providers, paper: Paper
) -> dict[str, list[Candidate]] | None:
    """None when Semantic Scholar doesn't know the paper."""
    key = await discovery.s2_key(providers.client("semantic_scholar"), paper.doi, paper.title)
    if key is None:
        return None
    cites = await semantic_scholar.references(providers.client("semantic_scholar"), key, REFS_CAP)
    if cites is None:
        return None
    cited_by = await semantic_scholar.citations(providers.client("semantic_scholar"), key, CITING_CAP) or []
    return {"cites": [from_s2(p) for p in cites], "cited_by": [from_s2(p) for p in cited_by]}


async def _from_openalex(providers: source_clients.Providers, paper: Paper) -> dict[str, list[Candidate]]:
    ids = await openalex.referenced_works(providers.client("openalex"), paper.openalex_id)
    cites = await openalex.works_by_ids(providers.client("openalex"), ids[:REFS_CAP])
    cited_by = await openalex.citing_works(providers.client("openalex"), paper.openalex_id, CITING_CAP)
    return {"cites": [from_work(w) for w in cites], "cited_by": [from_work(w) for w in cited_by]}


async def fetch(session: AsyncSession, providers: source_clients.Providers, paper: Paper) -> list[str]:
    """Stores both directions for `paper` and returns a notice per source that failed. Raises Conflict when no
    source could answer: none is on, the sources don't know the paper, or every one failed."""
    found: dict[str, dict[str, list[Candidate]]] = {}  # source -> direction -> candidates, most trusted first
    notices: list[str] = []
    unknown = False
    asks = []
    if providers.client("openalex") is not None and paper.openalex_id:
        asks.append(("openalex", _from_openalex))
    if providers.client("semantic_scholar") is not None:
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
    await session.execute(_TAKE_LOCK, {"key": REFERENCES_LOCK})  # after the network calls: held until the commit
    for direction, cap in (("cites", REFS_CAP), ("cited_by", CITING_CAP)):
        # A record with no id at all (Semantic Scholar lists some) can't be matched, imported or co-cited: not stored.
        identified = {
            source: [c for c in lists[direction] if _same_reference(c.external_ids, c.doi)]
            for source, lists in found.items()
        }
        merged = merge(identified, cap)
        if direction == "cited_by":  # newest first, as the reverse direction is read (addendum §3d)
            merged = sorted(merged, key=lambda c: -(c.year or 0))
        await session.execute(
            delete(paper_references).where(
                paper_references.c.paper_id == paper.id, paper_references.c.direction == direction
            )
        )
        for position, candidate in enumerate(merged):
            # Linked right after its row is stored, so a later candidate that folds this row moves the link with it.
            ref_id = await _upsert(session, candidate)
            link = {"paper_id": paper.id, "ref_id": ref_id, "direction": direction, "position": position}
            await session.execute(pg_insert(paper_references).values(**link).on_conflict_do_nothing())
    await session.commit()
    return notices


async def _upsert(session: AsyncSession, candidate: Candidate) -> uuid.UUID:
    """The stored reference for `candidate`, created or refreshed. Rows that turn out to be the same paper (one known
    by its Semantic Scholar id, another by its DOI) fold into the oldest, and an imported row always wins."""
    matches = _same_reference(candidate.external_ids, candidate.doi)
    existing = []
    if matches:  # or_() of nothing compiles to no WHERE, which would fold every stored reference into this one
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
    if not existing:
        return await session.scalar(
            insert(ExternalRef)
            .values(**fields, pdf_urls=candidate.pdf_urls, doi=candidate.doi, external_ids=dict(candidate.external_ids))
            .returning(ExternalRef.id)
        )
    keeper, *duplicates = existing
    # Candidate's own value wins; a duplicate fills what's still missing; the keeper's pre-existing value fills
    # what's still missing after that — the same three-tier precedence the old per-field `ids[name] = ids[name]
    # or getattr(duplicate, name)` loop gave, now as dict merges since "key absent" replaces "value is None".
    external_ids = dict(candidate.external_ids)
    doi = candidate.doi
    for duplicate in duplicates:
        external_ids = {**duplicate.external_ids, **external_ids}
        doi = doi or duplicate.doi
        await _repoint(session, duplicate.id, keeper.id)
        await session.delete(duplicate)
    await session.flush()
    external_ids = {**keeper.external_ids, **external_ids}
    doi = doi or keeper.doi
    if candidate.title != keeper.title:  # a new title needs a new vector
        fields |= {"title_embedding": None, "title_embed_model": None}
    # Preserve PDF URLs from candidate, duplicates, and keeper when folding
    fields["pdf_urls"] = ordered_pdf_urls(
        external_ids.get("arxiv"),
        *candidate.pdf_urls,
        *(url for row in [*duplicates, keeper] for url in row.pdf_urls),
    )
    earliest = min((row.queued_at for row in duplicates if row.queued_at is not None), default=None)
    if earliest is not None:  # D120: a fold keeps the earliest To read; the keeper's own value is read in SQL
        fields = {**fields, "queued_at": func.least(ExternalRef.queued_at, earliest)}
    await session.execute(
        update(ExternalRef).where(ExternalRef.id == keeper.id).values(**fields, doi=doi, external_ids=external_ids)
    )
    return keeper.id


def _same_reference(external_ids: dict[str, str], doi: str | None) -> list:
    """Conditions matching any stored reference that shares an id; [] when there is no id to match on."""
    conditions = [ExternalRef.external_ids[source].astext == value for source, value in external_ids.items()]
    if doi:
        conditions.append(func.lower(ExternalRef.doi) == doi.lower())
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


# --- To read (D164) ----------------------------------------------------------------------------------------------


async def queue(session: AsyncSession, ref_id: uuid.UUID) -> datetime:
    """Marks a reference To read. A second call keeps the first time. Nothing but this, a fold and an import writes
    queued_at, so a Refresh keeps it. Raises NotFound."""
    queued_at = await session.scalar(
        update(ExternalRef)
        .where(ExternalRef.id == ref_id)
        .values(queued_at=func.coalesce(ExternalRef.queued_at, func.now()))
        .returning(ExternalRef.queued_at)
    )
    if queued_at is None:
        raise NotFound(f"reference {ref_id} not found")
    await session.commit()
    return queued_at


async def unqueue(session: AsyncSession, ref_id: uuid.UUID) -> None:
    """Takes a reference off To read. Harmless when it isn't on it. Raises NotFound."""
    found = await session.scalar(
        update(ExternalRef).where(ExternalRef.id == ref_id).values(queued_at=None).returning(ExternalRef.id)
    )
    if found is None:
        raise NotFound(f"reference {ref_id} not found")
    await session.commit()


# --- embeddings --------------------------------------------------------------------------------------------------


# --- listing -----------------------------------------------------------------------------------------------------


# --- import ------------------------------------------------------------------------------------------------------


async def import_reference(
    session: AsyncSession, providers: source_clients.Providers, ref_id: uuid.UUID, pdf_dir: Path
) -> Paper:
    """Downloads the reference's first free PDF and creates the paper, as Find papers' Add does (D84). The caller
    enqueues ingest. The new paper's own references are not fetched (P5)."""
    ref = await session.get(ExternalRef, ref_id)
    if ref is None:
        raise NotFound(f"reference {ref_id} not found")
    if ref.imported_as is not None:
        raise Conflict(free_copy.ALREADY_IN_LIBRARY)
    candidate = Candidate(
        title=ref.title, authors=ref.authors, year=ref.year, venue=ref.venue, doi=ref.doi,
        external_ids=dict(ref.external_ids), cited_by_count=ref.cited_by_count, pdf_urls=ref.pdf_urls,
    )  # fmt: skip
    # Only doi/arxiv matter for this match, same as before — not every identifier, deliberately.
    arxiv_only = {"arxiv": ref.external_ids["arxiv"]} if "arxiv" in ref.external_ids else {}
    same_paper = [ExternalRef.id == ref_id, *_same_reference(arxiv_only, ref.doi)]

    async def mark_imported(paper_id: uuid.UUID) -> None:
        # Dealt with: deleting the paper later won't put it back in To read (D164).
        await session.execute(update(ExternalRef).where(or_(*same_paper)).values(imported_as=paper_id, queued_at=None))
        await session.commit()

    try:
        paper = await discovery.add(session, providers, candidate, pdf_dir)
    except Conflict as exc:
        if str(exc) == free_copy.ALREADY_IN_LIBRARY and "paper_id" in exc.details:  # the library holds its arXiv copy
            await mark_imported(exc.details["paper_id"])
        raise
    await mark_imported(paper.id)
    return paper
