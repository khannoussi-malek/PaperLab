"""Paper metadata from three sources, in rising precedence: the PDF, OpenAlex, the user.

- Never fatal: a paper with no OpenAlex match, or with OpenAlex unreachable, stays fully usable.
- A stored OpenAlex ID, a DOI or an arXiv ID is trusted. A title-search hit is accepted only when its year (±1) and
  its first author agree with the PDF.
- Authors are keyed on OpenAlex IDs, never on names. Author details are refetched only after 30 days.
- A field the user corrected (papers.manual_fields) is never overwritten by the PDF or by OpenAlex.
"""

import html
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, InvalidInput
from app.core.papers import abstract_drafts, get_paper, replace_chunks
from app.core.provenance import stamp, stamp_edited
from app.core.source_types import (
    ARXIV_DOI_PREFIX,
    PREPRINT_SERVERS,
    is_preprint_copy,
    peer_reviewed_of,
    source_type_of,
)
from app.models import Author, Paper, PaperStatus, paper_authors, paper_topics
from app.providers import crossref, openalex

logger = logging.getLogger(__name__)

AUTHOR_REFRESH_AFTER = timedelta(days=30)
YEAR_TOLERANCE = 1  # an arXiv preprint and its published version are often dated a year apart

_DOI = re.compile(r"10\.\d{4,9}/\S+")
# New-style ("1810.04805") or old-style, pre-2007 ("hep-th/9901001", "math.GT/0309136") IDs, an optional "vN" dropped.
_ARXIV_ID = re.compile(r"arXiv:(\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7})(?:v\d+)?", re.IGNORECASE)
_PDF_DATE_YEAR = re.compile(r"D:(\d{4})")
# ponytail: splits "A; B and C" and "A, B". A "Family, Given" author field becomes two names; the user can correct it.
_AUTHOR_SEPARATORS = re.compile(r"\s*(?:;|,|\band\b)\s*")
_KEYWORD_SEPARATORS = re.compile(r"\s*[;,]\s*")


@dataclass(frozen=True)
class PdfHints:
    doi: str | None
    arxiv_id: str | None
    years: frozenset[int]  # years the PDF suggests: its arXiv ID's year and its creation date's year
    text: str  # the embedded author field and page 1's text, where a match's first author must appear
    authors: list[str]  # the embedded author field, split into names
    keywords: list[str]  # the embedded keywords: the author's own topic labels


@dataclass(frozen=True)
class Collision:
    """A doi or openalex_id `_write` dropped because another paper (`holder_id`) already holds it."""

    column: str
    value: str
    holder_id: uuid.UUID


def normalize_doi(value: str) -> str | None:
    """The first DOI in `value`, lowercased (DOIs are case-insensitive), or None."""
    match = _DOI.search(value)
    if match is None:
        return None
    doi = re.sub(r"^(10\.\d{4,9})/+", r"\1/", match.group().lower())  # OpenAlex's legacy APA "10.1037//…"
    while True:
        trimmed = doi.rstrip(".,;").removesuffix(".pdf")  # a publisher's PDF URL ends in the file's extension
        # A DOI may contain balanced brackets ("s0140-6736(20)30367-6"); only an unbalanced closing one is prose.
        for open_ch, close_ch in ("()", "[]"):
            if trimmed.endswith(close_ch) and trimmed.count(close_ch) > trimmed.count(open_ch):
                trimmed = trimmed[:-1]
        if trimmed == doi:
            return trimmed
        doi = trimmed


def _split(value: str, separators: re.Pattern) -> list[str]:
    return [part for part in separators.split(value) if part]


def pdf_hints(first_page_text: str, metadata: dict[str, str]) -> PdfHints:
    arxiv = _ARXIV_ID.search(first_page_text)
    created = _PDF_DATE_YEAR.match(metadata.get("creationDate", ""))
    years = {int(created.group(1))} if created else set()
    if arxiv and "/" not in arxiv.group(1):
        years.add(2000 + int(arxiv.group(1)[:2]))  # new-style arXiv IDs start with yymm
    # ponytail: old-style IDs (archive/YYMMNNN) span 1991-2007, so a bare "2000 + yy" would misread them; skip.
    author = metadata.get("author", "")
    return PdfHints(
        doi=normalize_doi(" ".join([metadata.get("subject", ""), metadata.get("keywords", ""), first_page_text])),
        arxiv_id=arxiv.group(1) if arxiv else None,
        years=frozenset(years),
        text=f"{author}\n{first_page_text}",
        authors=_split(author, _AUTHOR_SEPARATORS),
        keywords=_split(metadata.get("keywords", ""), _KEYWORD_SEPARATORS),
    )


_UNICODE_HYPHENS = str.maketrans("‐‑", "--")  # OpenAlex writes "Ming‐Wei" with U+2010


def _fold(text: str) -> str:
    """Casefolded, without accents, ASCII hyphens: "Chabrière‐Smith" and "CHABRIERE-SMITH" compare equal."""
    text = unicodedata.normalize("NFKD", text).translate(_UNICODE_HYPHENS)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _on_page(family: str, hints: PdfHints) -> bool:
    # ponytail: the family name as a whole word on page 1. A name in a non-Latin script never matches: a miss,
    # never a wrong match.
    return bool(family) and re.search(rf"\b{re.escape(_fold(family))}\b", _fold(hints.text)) is not None


def _first_author_matches(work: dict[str, Any], hints: PdfHints) -> bool:
    authorships = work.get("authorships") or []
    names = authorships[0]["author"]["display_name"].split() if authorships else []
    return bool(names) and _on_page(names[-1], hints)


def is_confirmed_match(work: dict[str, Any], hints: PdfHints) -> bool:
    """A title-search hit counts only when its year and its first author agree with the PDF."""
    year = work.get("publication_year")
    if year is None or not any(abs(year - y) <= YEAR_TOLERANCE for y in hints.years):
        return False
    return _first_author_matches(work, hints)


def short_id(url: str | None) -> str | None:
    """ "https://openalex.org/W2963341956" -> "W2963341956"; also strips "https://orcid.org/"."""
    return url.rsplit("/", 1)[-1] if url else None


def abstract_text(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    return " ".join(word for _, word in sorted((i, word) for word, places in inverted_index.items() for i in places))


def work_fields(work: dict[str, Any]) -> dict[str, Any]:
    """The papers columns an OpenAlex work fills."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    best_oa = work.get("best_oa_location") or {}
    fields = {
        "openalex_id": short_id(work["id"]),
        "doi": normalize_doi(work.get("doi") or ""),
        "title": work.get("title"),
        "abstract": abstract_text(work.get("abstract_inverted_index")),
        "authors": [a["author"]["display_name"] for a in work.get("authorships") or []],
        "year": work.get("publication_year"),
        "venue": source.get("display_name") or location.get("raw_source_name"),
        "issn": source.get("issn_l"),
        "type": work.get("type"),
        "is_retracted": bool(work.get("is_retracted")),
        "oa_status": (work.get("open_access") or {}).get("oa_status"),
        "oa_url": best_oa.get("pdf_url") or best_oa.get("landing_page_url"),
        "cited_by_count": work.get("cited_by_count"),
        "referenced_works_count": work.get("referenced_works_count"),
    }
    return fields


def openalex_biblio(work: dict[str, Any]) -> dict[str, str | None]:
    """volume, issue, pages, pmid and pmcid (bare ids) of an OpenAlex work. Not in `work_fields`: these six columns are
    fill-only (see `fill_biblio`)."""
    biblio = work.get("biblio") or {}
    ids = work.get("ids") or {}
    pages = "-".join(dict.fromkeys(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p))
    return {
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages or None,
        "pmid": short_id((ids.get("pmid") or "").rstrip("/")),
        "pmcid": short_id((ids.get("pmcid") or "").rstrip("/")),
    }


BIBLIO_FIELDS = ("volume", "issue", "pages", "editors", "pmid", "pmcid")
PUBLISHED_TYPES = frozenset({"article", "conference-paper", "proceedings-article", "book-chapter"})


def openalex_published(work: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(published_doi, published_venue, source_type) when the work is a published version: a non-arXiv DOI, a
    published type (or a publishedVersion location) and a primary source that is no preprint server."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    venue = source.get("display_name") or location.get("raw_source_name")
    doi = normalize_doi(work.get("doi") or "")
    published = location.get("version") == "publishedVersion" or (work.get("type") or "").lower() in PUBLISHED_TYPES
    if not doi or doi.startswith(ARXIV_DOI_PREFIX) or not published:
        return None, None, None
    if source.get("type") == "repository" or (venue and PREPRINT_SERVERS.search(venue)):
        return None, None, None
    return doi, venue, source_type_of(work.get("type"), doi)


async def record_published(session: AsyncSession, paper_id: uuid.UUID, work: dict[str, Any]) -> None:
    """A preprint copy whose OpenAlex work is its published version gets published_doi, published_venue and
    peer_reviewed "true" (never its own doi/venue; `_write` keeps manual_fields)."""
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)
    doi, venue, _ = openalex_published(work)
    if not is_preprint_copy(paper) or doi in (None, normalize_doi(paper.doi or "")):
        return
    await _write(session, paper, {"published_doi": doi, "published_venue": venue, "peer_reviewed": "true"}, "openalex")


def work_topics(work: dict[str, Any]) -> dict[str, float]:
    """OpenAlex topics, keywords and concepts by label. A label in more than one list keeps its best score."""
    scores: dict[str, float] = {}
    for item in [*(work.get("topics") or []), *(work.get("keywords") or []), *(work.get("concepts") or [])]:
        scores[item["display_name"]] = max(scores.get(item["display_name"], 0.0), item["score"])
    return scores


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


async def _replace_authorships(session: AsyncSession, paper_id: uuid.UUID, work: dict[str, Any]) -> list[str]:
    """Upserts the work's authors by OpenAlex ID and links them in author order. Returns their OpenAlex IDs."""
    first_listing: dict[str, tuple[int, dict]] = {}
    for position, authorship in enumerate(work.get("authorships") or [], start=1):
        if openalex_id := short_id(authorship["author"].get("id")):  # never create an author from a name alone
            first_listing.setdefault(openalex_id, (position, authorship))
    await session.execute(delete(paper_authors).where(paper_authors.c.paper_id == paper_id))
    if not first_listing:
        return []

    new_authors = [
        {"openalex_id": oid, "display_name": a["author"]["display_name"], "orcid": short_id(a["author"].get("orcid"))}
        for oid, (_, a) in first_listing.items()
    ]
    # ponytail: two OpenAlex IDs sharing one ORCID break authors.orcid UNIQUE, and the paper keeps no authors (still
    # non-fatal). Drop the ORCID on conflict if OpenAlex's duplicate profiles ever show up.
    await session.execute(pg_insert(Author).values(new_authors).on_conflict_do_nothing(index_elements=["openalex_id"]))
    rows = await session.execute(select(Author.openalex_id, Author.id).where(Author.openalex_id.in_(first_listing)))
    author_ids = dict(rows.all())
    links = [
        {
            "paper_id": paper_id,
            "author_id": author_ids[oid],
            "position": position,
            "is_corresponding": bool(a.get("is_corresponding")),
            # The affiliation printed on this paper, not the author's current one.
            "institution": next((i["display_name"] for i in a.get("institutions") or []), None),
        }
        for oid, (position, a) in first_listing.items()
    ]
    await session.execute(insert(paper_authors), links)
    return list(first_listing)


async def refresh_authors(session: AsyncSession, http: httpx.AsyncClient, openalex_ids: list[str]) -> None:
    """Fetches details (h-index, works count, ...) for authors not fetched in the last 30 days, 50 per request."""
    stale = list(
        await session.scalars(
            select(Author.openalex_id).where(
                Author.openalex_id.in_(openalex_ids),
                or_(Author.fetched_at.is_(None), Author.fetched_at < func.now() - AUTHOR_REFRESH_AFTER),
            )
        )
    )
    if not stale:
        return
    stale.sort(key=openalex_ids.index)  # author order, so requests are predictable
    for record in await openalex.get_authors(http, stale):
        values = {
            "display_name": record["display_name"],
            "orcid": short_id(record.get("orcid")),
            "alt_names": record.get("display_name_alternatives") or [],
            "last_institution": next((i["display_name"] for i in record.get("last_known_institutions") or []), None),
            "works_count": record.get("works_count"),
            "cited_by_count": record.get("cited_by_count"),
            "h_index": (record.get("summary_stats") or {}).get("h_index"),
            "topics": [{"label": t["display_name"], "count": t.get("count")} for t in record.get("topics") or []],
            "fetched_at": func.now(),
        }
        await session.execute(update(Author).where(Author.openalex_id == short_id(record["id"])).values(**values))
    await session.commit()


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


async def _crossref_work(http: httpx.AsyncClient, doi: str, cache: dict[str, dict | None]) -> dict | None:
    """One Crossref fetch per DOI per `cache`; a failed fetch is remembered too, then re-raised."""
    if doi not in cache:
        cache[doi] = None
        cache[doi] = await crossref.get_work(http, doi)
    return cache[doi]


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


def crossref_biblio(work: dict[str, Any]) -> dict[str, Any]:
    """volume, issue, pages and editors from a Crossref work; editors are "Given Family" names."""
    editors = [
        (e.get("name") or f"{e.get('given', '')} {e.get('family', '')}").strip() for e in work.get("editor") or []
    ]
    fields = {k: work.get(src) for k, src in (("volume", "volume"), ("issue", "issue"), ("pages", "page"))}
    return {**fields, "editors": [e for e in editors if e] or None}


def _crossref_year(work: dict[str, Any]) -> int | None:
    for key in ("published-print", "issued"):  # the issue's date, else the earliest
        [year, *_] = ((work.get(key) or {}).get("date-parts") or [[None]])[0] or [None]
        if year:
            return int(year)
    return None


ALIGN_TYPES = frozenset({"journal-article", "proceedings-article"})  # where container-title is the venue
_PAGE_RANGE = re.compile(r"(\d+)\s*[-\u2013]\s*(\d+)")


def _alignable(paper: Paper) -> bool:
    """Not a preprint copy (it keeps its own year), and a DOI known to be the paper's own: matched by OpenAlex, set
    by the owner, given with a paper saved without a PDF, or not read off page 1 (which can carry a cited paper's)."""
    trusted = (
        paper.openalex_id is not None
        or "doi" in paper.manual_fields
        or paper.file_path is None
        or (paper.field_sources or {}).get("identifiers") != "pdf"
    )
    return trusted and not is_preprint_copy(paper)


def align_with_crossref(paper: Paper, work: dict[str, Any]) -> dict[str, Any]:
    """Corrections from the Crossref work for the paper's own DOI (`_alignable`). For a journal or proceedings article,
    the issue year (published-print, else issued) over an online-first or preprint year, and the journal's name at the
    time (a single container-title) over its current one. For any type, a plain "a-b" page range over its lone first
    page. Never title, authors or DOI, and never a manual field."""
    if not _alignable(paper):
        return {}
    titles = work.get("container-title") or []
    article = work.get("type") in ALIGN_TYPES
    venue = (html.unescape(titles[0] or "").strip() or None) if article and len(titles) == 1 else None
    page = _PAGE_RANGE.fullmatch((work.get("page") or "").strip())
    lone_first = page and (paper.pages or "").strip() == page[1] != page[2]
    found = {
        "year": _crossref_year(work) if article else None,
        "venue": venue,
        "pages": f"{page[1]}-{page[2]}" if lone_first else None,
    }
    return {k: v for k, v in found.items() if v and v != getattr(paper, k) and k not in paper.manual_fields}


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
    from app.core.candidates import from_crossref, normal_title  # noqa: PLC0415 (candidates imports this module)

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
