"""Paper metadata from three sources, in rising precedence: the PDF, OpenAlex, the user.

- Never fatal: a paper with no OpenAlex match, or with OpenAlex unreachable, stays fully usable.
- A stored OpenAlex ID, a DOI or an arXiv ID is trusted. A title-search hit is accepted only when its year (±1) and
  its first author agree with the PDF.
- Authors are keyed on OpenAlex IDs, never on names. Author details are refetched only after 30 days.
- A field the user corrected (papers.manual_fields) is never overwritten by the PDF or by OpenAlex.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.author_refresh import _replace_authorships, refresh_authors
from app.core.papers.crossref_align import _alignable, _crossref_work, align_with_crossref, crossref_biblio
from app.core.papers.openalex_fields import openalex_biblio, openalex_published, work_fields, work_topics
from app.core.papers.papers import abstract_drafts, get_paper, replace_chunks
from app.core.papers.pdf_hints import YEAR_TOLERANCE, PdfHints, _first_author_matches, _on_page, is_confirmed_match
from app.core.papers.provenance import stamp, stamp_edited
from app.domain.doi import normalize_doi
from app.domain.errors import Conflict, InvalidInput
from app.domain.source_types import (
    ARXIV_DOI_PREFIX,
    is_preprint_copy,
    peer_reviewed_of,
    source_type_of,
)
from app.models import Paper, PaperStatus, paper_topics
from app.providers import openalex

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Collision:
    """A doi or openalex_id `_write` dropped because another paper (`holder_id`) already holds it."""

    column: str
    value: str
    holder_id: uuid.UUID


async def record_published(session: AsyncSession, paper_id: uuid.UUID, work: dict[str, Any]) -> None:
    """A preprint copy whose OpenAlex work is its published version gets published_doi, published_venue and
    peer_reviewed "true" (never its own doi/venue; `_write` keeps manual_fields)."""
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)
    doi, venue, _ = openalex_published(work)
    if not is_preprint_copy(paper) or doi in (None, normalize_doi(paper.doi or "")):
        return
    await _write(session, paper, {"published_doi": doi, "published_venue": venue, "peer_reviewed": "true"}, "openalex")


async def find_work(http: httpx.AsyncClient, paper: Paper, hints: PdfHints) -> dict[str, Any] | None:
    """The stored openalex_id and a manually corrected DOI are trusted outright: the user (or an earlier confirmed
    match) vouched for them. A DOI merely hinted by the PDF -- or left over from an earlier unconfirmed fallback
    write -- and an arXiv ID from the PDF must also pass the first-author check; a miss falls through to title
    search. Raises httpx.HTTPError when OpenAlex fails.
    """
    trusted_doi = paper.doi if paper.doi and "doi" in paper.manual_fields else None
    for key in filter(None, [paper.openalex_id, trusted_doi and f"doi:{trusted_doi}"]):
        if work := await openalex.get_work(http, key):
            return work

    hinted_doi = None if trusted_doi else (paper.doi or hints.doi)
    hinted_keys = [hinted_doi and f"doi:{hinted_doi}", hints.arxiv_id and f"doi:{ARXIV_DOI_PREFIX}{hints.arxiv_id}"]
    for key in filter(None, hinted_keys):
        if (work := await openalex.get_work(http, key)) and _first_author_matches(work, hints):
            return work

    if not hints.years:
        return None  # a hit could never be confirmed, so don't spend 10 credits on the search
    return next((w for w in await openalex.search_works(http, paper.title) if is_confirmed_match(w, hints)), None)


async def _replace_topics(session: AsyncSession, paper_id: uuid.UUID, source: str, scores: dict) -> None:
    topics = paper_topics.c
    await session.execute(delete(paper_topics).where(topics.paper_id == paper_id, topics.source == source))
    if scores:
        rows = [{"paper_id": paper_id, "source": source, "label": label, "score": s} for label, s in scores.items()]
        await session.execute(insert(paper_topics), rows)


def _regresses(new: Any, old: Any) -> bool:
    """True when a match or the PDF fallback would replace an already-known value with a blank."""
    return new in (None, []) and old not in (None, [])


async def _taken(session: AsyncSession, paper_id: uuid.UUID, column: Any, value: Any) -> uuid.UUID | None:
    """The different paper already holding this UNIQUE `column` value, or None."""
    # ponytail: check-then-UPDATE, not atomic. ARQ runs up to 10 jobs at once, so two concurrent duplicates could
    # still both pass this check and hit the UNIQUE constraint on the later UPDATE; the worker's `_enrich` catch-all
    # logs it and the paper still ends `ready`. Upgrade path: `ON CONFLICT` on the UPDATE, or a savepoint around
    # check+write.
    return await session.scalar(select(Paper.id).where(column == value, Paper.id != paper_id))


async def _write(
    session: AsyncSession, paper: Paper, fields: dict[str, Any], source: str, *, keep_manual_stamps: bool = False
) -> list[Collision]:
    """Writes `fields` past the guards below, stamping `source` on the groups actually written (R22); with
    `keep_manual_stamps`, a group the owner edited keeps its "manual" stamp."""
    # The OpenAlex lookup can take seconds; re-read the lock right before writing, in case a PATCH landed meanwhile.
    await session.refresh(paper, ["manual_fields", "field_sources"])
    values = {k: v for k, v in fields.items() if k not in paper.manual_fields and not _regresses(v, getattr(paper, k))}
    if "source_type" in paper.manual_fields:  # peer_reviewed was derived from a type the owner replaced
        values.pop("peer_reviewed", None)
    # A duplicate upload can match the very work (or carry the very DOI) an existing paper already holds; doi and
    # openalex_id are both UNIQUE, so a value another paper already has is dropped here instead of raising. The
    # copy still gets the match's authorships and topics: those are written regardless, keyed on paper_id, not on
    # the papers.openalex_id column this function may have just dropped. Each one dropped is returned.
    collisions = []
    for column, key in ((Paper.doi, "doi"), (Paper.openalex_id, "openalex_id")):
        if (value := values.get(key)) and (holder_id := await _taken(session, paper.id, column, value)):
            values = {k: v for k, v in values.items() if k != key}
            collisions.append(Collision(key, value, holder_id))
    if values:
        manual = {g for g, s in (paper.field_sources or {}).items() if s == "manual"} if keep_manual_stamps else set()
        await session.execute(update(Paper).where(Paper.id == paper.id).values(**stamp(values, source, skip=manual)))
    return collisions


async def fill_source_type(
    session: AsyncSession,
    paper_id: uuid.UUID,
    raw_type: str | None,
    crossref_http: httpx.AsyncClient | None,
    crossref_works: dict[str, dict | None] | None = None,
) -> bool:
    """Sets source_type, peer_reviewed and published_doi (never past the owner's lock). `raw_type` is OpenAlex's type;
    without one, a non-arXiv DOI is asked of Crossref (when `crossref_http` is given). A paper that already has a
    source type is not asked again. Crossref errors are logged, never raised. True when Crossref was asked."""
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)
    doi = normalize_doi(paper.doi or "")
    fields: dict[str, Any] = {}
    asked = False
    # The arXiv DOI rule needs no source's word for it (source_type_of); otherwise OpenAlex's type, else Crossref's.
    source = "arxiv" if (doi or "").startswith(ARXIV_DOI_PREFIX) else "openalex"
    if (source_type := source_type_of(raw_type, doi)) is None and paper.source_type is None and doi and crossref_http:
        asked, source = True, "crossref"
        try:
            work = await _crossref_work(crossref_http, doi, {} if crossref_works is None else crossref_works)
            if work:
                source_type = source_type_of(work.get("type"), doi, crossref=True)
                preprint_of = ((work.get("relation") or {}).get("is-preprint-of") or [{}])[0].get("id")
                fields["published_doi"] = normalize_doi(preprint_of or "")
        except (httpx.HTTPError, KeyError, TypeError, AttributeError) as exc:  # a reply without "message", odd shapes
            logger.warning("Crossref lookup failed for paper %s, source type left as is: %r", paper_id, exc)
            source_type, fields = None, {}
    if source_type:
        fields |= {"source_type": source_type, "peer_reviewed": peer_reviewed_of(source_type)}
    if paper.published_venue or paper.published_doi:  # enrich_papers found it published: not a preprint to rate
        fields.pop("peer_reviewed", None)
    if fields:
        await _write(session, paper, fields, source)
        await session.commit()
    return asked


async def fill_biblio(
    session: AsyncSession,
    paper_id: uuid.UUID,
    crossref_http: httpx.AsyncClient | None,
    openalex_http: httpx.AsyncClient | None = None,
    *,
    openalex_work: dict[str, Any] | None = None,
    crossref_works: dict[str, dict | None] | None = None,
    align: bool = True,
) -> bool:
    """Fills volume, issue, pages, editors, pmid and pmcid that are still NULL, never past manual_fields and never over
    a value already held. Crossref wins over OpenAlex. With `align`, Crossref's year, venue and page range also correct
    the stored ones (`align_with_crossref`, only on a DOI it trusts), each change logged. `openalex_work` is a work
    already fetched; `crossref_works` is the per-enrichment cache shared with `fill_source_type`. Source errors are
    logged, never raised. True when a request went out."""
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)
    doi = normalize_doi(paper.doi or "")
    cache = {} if crossref_works is None else crossref_works
    found: dict[str, Any] = {}
    corrections: dict[str, Any] = {}
    asked = False
    crossref_fields = ("volume", "issue", "pages", "editors")
    align = align and _alignable(paper)
    if (
        doi
        and crossref_http
        and not doi.startswith(ARXIV_DOI_PREFIX)
        and (align or any(getattr(paper, f) is None for f in crossref_fields))
    ):
        asked = doi not in cache
        try:
            work = await _crossref_work(crossref_http, doi, cache) or {}
            found |= crossref_biblio(work)
            corrections = align_with_crossref(paper, work) if align and work else {}
        except (httpx.HTTPError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("Crossref biblio lookup failed for paper %s: %r", paper_id, exc)
    wanted = ("volume", "issue", "pages", "pmid", "pmcid")
    key = paper.openalex_id or (doi and f"doi:{doi}")
    if openalex_work is None and openalex_http and key and any(getattr(paper, f) is None for f in wanted):
        asked = True
        try:
            openalex_work = await openalex.get_work(openalex_http, key)
        except (httpx.HTTPError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("OpenAlex biblio lookup failed for paper %s: %r", paper_id, exc)
    from_crossref = {k for k, v in found.items() if v}
    if openalex_work:
        found = {k: v for k, v in openalex_biblio(openalex_work).items() if v} | {k: v for k, v in found.items() if v}
    fields = {k: v for k, v in found.items() if v and getattr(paper, k) is None}
    if fields:
        for source in ("openalex", "crossref"):  # OpenAlex first, so a group both filled reads Crossref, the winner
            if part := {k: v for k, v in fields.items() if (k in from_crossref) == (source == "crossref")}:
                await _write(session, paper, part, source)
    if corrections:  # a lone first page is never NULL, so these never overlap the fills above
        for field, value in corrections.items():
            logger.info("Crossref aligns %s of paper %s: %r -> %r", field, paper_id, getattr(paper, field), value)
        await _write(session, paper, corrections, "crossref", keep_manual_stamps=True)
    if fields or corrections:
        await session.commit()
    return asked


async def _fill_from_crossref(
    session: AsyncSession,
    paper_id: uuid.UUID,
    hints: PdfHints,
    crossref_http: httpx.AsyncClient | None,
    crossref_works: dict[str, dict | None],
) -> None:
    """Blank authors, year and venue from Crossref's record for the paper's DOI, when OpenAlex matched nothing. A DOI
    found on page 1 can be a cited paper's, so only when Crossref's first author's family name is on page 1 and its
    year is within a year of the PDF's (as `is_confirmed_match`) or its title is the paper's."""
    from app.core.search.candidates import normal_title
    from app.core.search.from_indexes import from_crossref  # noqa: PLC0415 (candidates imports this module)

    paper = await get_paper(session, paper_id)
    await session.refresh(paper)
    doi = normalize_doi(paper.doi or "")
    blank = paper.authors in (None, []) or paper.year is None or paper.venue is None
    if not (doi and crossref_http and blank) or doi.startswith(ARXIV_DOI_PREFIX):
        return
    try:
        work = await _crossref_work(crossref_http, doi, crossref_works) or {}
        found = from_crossref(work) if work else None  # None: not a paper
        family = ((work.get("author") or [{}])[0] or {}).get("family") or ""
    except (httpx.HTTPError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("Crossref metadata lookup failed for paper %s: %r", paper_id, exc)
        return
    if found is None or not _on_page(family, hints):
        return
    same_year = found.year is not None and any(abs(found.year - y) <= YEAR_TOLERANCE for y in hints.years)
    if not same_year and normal_title(found.title) != normal_title(paper.title or ""):
        return
    known = {"authors": found.authors, "year": found.year, "venue": found.venue}
    if fields := {k: v for k, v in known.items() if v and getattr(paper, k) in (None, [])}:
        await _write(session, paper, fields, "crossref")
        await session.commit()


async def enrich_paper(
    session: AsyncSession,
    http: httpx.AsyncClient | None,
    paper_id: uuid.UUID,
    hints: PdfHints,
    crossref_http: httpx.AsyncClient | None = None,
) -> list[Collision]:
    """Fills a paper's metadata from OpenAlex, or from the PDF when OpenAlex has nothing. No client: OpenAlex is off.

    OpenAlex failures are logged and fall back to the PDF. A DOI or `openalex_id` another paper already holds is
    dropped instead of raising (see `_write`), and returned: the after-ingest merge (R17) reads them.
    """
    crossref_works: dict[str, dict | None] = {}  # one /works/{doi} fetch shared by fill_source_type and fill_biblio
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)  # the pipeline changed the title with a bulk UPDATE since this object was loaded
    try:
        work = await find_work(http, paper, hints) if http else None
    except httpx.HTTPError as exc:
        logger.warning("OpenAlex lookup failed for paper %s, using PDF metadata: %r", paper_id, exc)
        work = None

    await _replace_topics(session, paper_id, "author", dict.fromkeys(hints.keywords))
    if work is None:
        collisions = []
        if paper.openalex_id is None:
            fallback = {k: v for k, v in {"authors": hints.authors, "doi": hints.doi}.items() if v}
            if fallback:
                collisions = await _write(session, paper, fallback, "pdf")  # never replaces what an earlier match found
        await session.commit()
        await fill_source_type(session, paper_id, None, crossref_http, crossref_works)
        # OpenAlex vouched for nothing here, and _alignable can't tell a DOI ingest saw on page 1 when it bears no
        # "pdf" stamp (an older copy's). Only _fill_from_crossref's checked fill may set year and venue.
        await fill_biblio(session, paper_id, crossref_http, crossref_works=crossref_works, align=False)
        await _fill_from_crossref(session, paper_id, hints, crossref_http, crossref_works)
        return collisions

    collisions = await _write(session, paper, work_fields(work), "openalex")
    await _replace_topics(session, paper_id, "openalex", work_topics(work))
    await record_published(session, paper_id, work)
    await session.commit()
    await fill_source_type(session, paper_id, work.get("type"), crossref_http, crossref_works)
    await fill_biblio(session, paper_id, crossref_http, openalex_work=work, crossref_works=crossref_works)
    author_ids = await _replace_authorships(session, paper_id, work)
    await session.commit()
    try:
        await refresh_authors(session, http, author_ids)
    except httpx.HTTPError as exc:  # the paper and its authorships are saved; details come on the next run
        logger.warning("OpenAlex author fetch failed for paper %s: %r", paper_id, exc)
    return collisions


async def correct_metadata(session: AsyncSession, paper_id: uuid.UUID, fields: dict[str, Any]) -> Paper:
    """The user's corrections, written as given and added to manual_fields so nothing overwrites them later.

    `fields` holds only what the user changed. Raises NotFound, InvalidInput (a DOI that isn't one) or
    Conflict("doi_taken"). A paper without a PDF gets its abstract chunk rebuilt when the title or abstract changes:
    `embedding` again (the route enqueues index_abstract), or `ready` with no chunk when the abstract is cleared.
    """
    paper = await get_paper(session, paper_id)
    clears_match = {}
    if fields.get("doi") is not None:
        doi = normalize_doi(fields["doi"])
        if doi is None:
            raise InvalidInput(f"not a DOI: {fields['doi']!r}")
        if await session.scalar(select(Paper.id).where(Paper.doi == doi, Paper.id != paper_id)):
            raise Conflict("doi_taken")
        fields = {**fields, "doi": doi}
        if doi != paper.doi:
            # A different DOI can only mean the stored match (if any) is for the wrong paper. Not locked in
            # manual_fields: enrichment stays free to write back whatever the corrected DOI actually resolves to.
            clears_match = {"openalex_id": None, "published_checked_at": None}  # enrich_papers asks again
    manual_fields = sorted(set(paper.manual_fields) | fields.keys())
    rebuild = not paper.has_pdf and not {"title", "abstract"}.isdisjoint(fields)
    abstract = ((fields["abstract"] if "abstract" in fields else paper.abstract) or "").strip() or None
    reindex = {"status": PaperStatus.EMBEDDING if abstract else PaperStatus.READY} if rebuild else {}
    await session.execute(
        update(Paper)
        .where(Paper.id == paper_id)
        .values(**fields, **clears_match, **reindex, **stamp_edited(fields), manual_fields=manual_fields)
    )
    if rebuild:  # the abstract chunk is what search and chat read; the caller enqueues index_abstract when embedding
        await replace_chunks(session, paper_id, abstract_drafts(fields.get("title", paper.title), abstract))
    else:
        await session.commit()
    await session.refresh(paper)
    return paper
