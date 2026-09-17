"""Papers found outside the library: one candidate per source record, merged into one list (M19, M19.5).

- PDF URLs: arXiv by ID first, then each record's links in order; landing pages are never listed (D68).
- Merging (D73): records sharing a DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID or CORE ID are one paper, and so
  are records with the same title and a shared author surname. Fields come from the most trusted record that has them.
"""

import re
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from app.core.enrichment import ARXIV_DOI_PREFIX, short_id

# CandidateIn (app/schemas/discovery.py) rejects a candidate over either limit with 422; capping here first means
# the Add button never shows for a candidate its own endpoint would then refuse.
MAX_PDF_URLS = 10
MAX_AUTHORS = 500
# Crossref's title search also returns songs, datasets and peer reviews ("All You Need Is LSD" is type "other").
CROSSREF_PAPER_TYPES = frozenset(
    {"journal-article", "proceedings-article", "posted-content", "book-chapter", "book", "monograph", "report",
     "dissertation"}
)  # fmt: skip

ARXIV_ID = r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7}"
_ARXIV_URL = re.compile(rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})", re.IGNORECASE)
_ARXIV_VERSION = re.compile(r"v\d+$")


@dataclass(frozen=True)
class Candidate:
    """A paper found outside the library. `sources` lists every source that found it, most trusted first; `paper_id`
    is set when the library already holds it."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    core_id: str | None = None
    cited_by_count: int | None = None
    pdf_urls: list[str] = field(default_factory=list)
    sources: tuple[str, ...] = ()
    paper_id: uuid.UUID | None = None


def arxiv_from_doi(doi: str | None) -> str | None:
    return doi.removeprefix(ARXIV_DOI_PREFIX) if doi and doi.startswith(ARXIV_DOI_PREFIX) else None


def _arxiv_from_url(url: str | None) -> str | None:
    match = _ARXIV_URL.search(url or "")
    return match.group(1).lower() if match else None


def ordered_pdf_urls(arxiv_id: str | None, *links: str | None) -> list[str]:
    """arXiv first, then `links` in order: deduplicated, http(s) only, capped at MAX_PDF_URLS (D68)."""
    urls = [f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None, *links]
    deduped = dict.fromkeys(url for url in urls if url and url.startswith(("http://", "https://")))
    return list(deduped)[:MAX_PDF_URLS]


def from_work(work: dict[str, Any]) -> Candidate:
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").lower() or None
    best = work.get("best_oa_location") or {}
    locations = work.get("locations") or []
    location_urls = [
        url for place in [best, *locations] for url in (place.get("landing_page_url"), place.get("pdf_url"))
    ]
    arxiv_id = arxiv_from_doi(doi) or next(filter(None, map(_arxiv_from_url, location_urls)), None)
    source = (work.get("primary_location") or {}).get("source") or {}
    authors = [a["author"]["display_name"] for a in work.get("authorships") or [] if a.get("author")]
    return Candidate(
        title=work.get("title") or "Untitled",
        authors=authors[:MAX_AUTHORS],
        year=work.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi,
        arxiv_id=arxiv_id,
        openalex_id=short_id(work.get("id")),
        cited_by_count=work.get("cited_by_count"),
        pdf_urls=ordered_pdf_urls(arxiv_id, best.get("pdf_url"), *(place.get("pdf_url") for place in locations)),
        sources=("openalex",),
    )


def from_s2(paper: dict[str, Any]) -> Candidate:
    ids = paper.get("externalIds") or {}
    doi = (ids.get("DOI") or "").lower() or None
    arxiv_id = (ids.get("ArXiv") or "").lower() or arxiv_from_doi(doi)
    return Candidate(
        title=paper.get("title") or "Untitled",
        authors=[a["name"] for a in paper.get("authors") or [] if a.get("name")][:MAX_AUTHORS],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        doi=doi,
        arxiv_id=arxiv_id,
        s2_id=paper.get("paperId"),
        cited_by_count=paper.get("citationCount"),
        pdf_urls=ordered_pdf_urls(arxiv_id, (paper.get("openAccessPdf") or {}).get("url")),
        sources=("semantic_scholar",),
    )


def with_s2(candidate: Candidate, paper: dict[str, Any] | None) -> Candidate:
    """A candidate with Semantic Scholar's arXiv ID and free PDF link added (D70). A lookup, so no new source."""
    if paper is None:
        return candidate
    found = from_s2(paper)
    arxiv_id = candidate.arxiv_id or found.arxiv_id
    return replace(
        candidate,
        arxiv_id=arxiv_id,
        s2_id=found.s2_id,
        pdf_urls=ordered_pdf_urls(arxiv_id, *found.pdf_urls, *candidate.pdf_urls),
    )


def from_arxiv(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/arxiv.py: its arXiv ID already has no version."""
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=entry["doi"],
        arxiv_id=entry["arxiv_id"],
        pdf_urls=ordered_pdf_urls(entry["arxiv_id"]),
        sources=("arxiv",),
    )


def from_crossref(item: Mapping[str, Any]) -> Candidate | None:
    """None for a record that isn't a paper. Crossref lists no free PDFs: its links are for text mining (D68)."""
    if item.get("type") not in CROSSREF_PAPER_TYPES:
        return None
    doi = (item.get("DOI") or "").lower() or None
    names = [
        " ".join(filter(None, (a.get("given"), a.get("family")))) or a.get("name") for a in item.get("author") or []
    ]
    [year, *_] = ((item.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    arxiv_id = arxiv_from_doi(doi)
    return Candidate(
        title=next(iter(item.get("title") or []), None) or "Untitled",
        authors=[name for name in names if name][:MAX_AUTHORS],
        year=year,
        venue=next(iter(item.get("container-title") or []), None),
        doi=doi,
        arxiv_id=arxiv_id,
        cited_by_count=item.get("is-referenced-by-count"),
        pdf_urls=ordered_pdf_urls(arxiv_id),
        sources=("crossref",),
    )


def from_core(work: Mapping[str, Any]) -> Candidate:
    """Only `downloadUrl` is a PDF link: CORE's other full-text URLs include landing pages (D68). Its citation count
    is left out, since CORE counted 0 for a paper cited 100,000 times."""
    doi = (work.get("doi") or "").lower() or None
    arxiv_id = _ARXIV_VERSION.sub("", (work.get("arxivId") or "").lower()) or arxiv_from_doi(doi)
    return Candidate(
        title=" ".join((work.get("title") or "").split()) or "Untitled",
        authors=[a["name"] for a in work.get("authors") or [] if a.get("name")][:MAX_AUTHORS],
        year=work.get("yearPublished"),
        doi=doi,
        arxiv_id=arxiv_id,
        core_id=str(work["id"]) if work.get("id") is not None else None,
        pdf_urls=ordered_pdf_urls(arxiv_id, work.get("downloadUrl")),
        sources=("core",),
    )


def normal_title(title: str) -> str:
    return re.sub(r"\W+", " ", title).strip().casefold()


def surname(name: str) -> str:
    """ "Uszkoreit, Jakob" and "Jakob Uszkoreit" both give "uszkoreit"; accents are dropped ("Krönke" → "kronke")."""
    part = name.split(",")[0] if "," in name else next(reversed(name.split()), "")
    return "".join(c for c in unicodedata.normalize("NFKD", part) if not unicodedata.combining(c)).strip().casefold()


def _ids(candidate: Candidate) -> set[str]:
    arxiv_id = candidate.arxiv_id or arxiv_from_doi(candidate.doi)
    keys = {
        "doi": None if arxiv_from_doi(candidate.doi) else candidate.doi,
        "arxiv": arxiv_id,
        "openalex": candidate.openalex_id,
        "s2": candidate.s2_id,
        "core": candidate.core_id,
    }
    return {f"{kind}:{value.lower()}" for kind, value in keys.items() if value}


def _same_paper(a: Candidate, b: Candidate) -> bool:
    if _ids(a) & _ids(b):
        return True
    if normal_title(a.title) != normal_title(b.title):
        return False
    if a.authors and b.authors:
        return bool({surname(n) for n in a.authors} & {surname(n) for n in b.authors})
    return a.year is not None and a.year == b.year


def _combined(records: list[Candidate]) -> Candidate:
    """`records` most trusted first: each field from the first record that has it."""

    def first(attribute: str):
        return next((value for r in records if (value := getattr(r, attribute))), None)

    arxiv_id = first("arxiv_id")
    counts = [r.cited_by_count for r in records if r.cited_by_count is not None]
    return Candidate(
        title=records[0].title,
        authors=first("authors") or [],
        year=first("year"),
        venue=first("venue"),
        doi=first("doi"),
        arxiv_id=arxiv_id,
        openalex_id=first("openalex_id"),
        s2_id=first("s2_id"),
        core_id=first("core_id"),
        cited_by_count=max(counts, default=None),
        pdf_urls=ordered_pdf_urls(arxiv_id, *(url for r in records for url in r.pdf_urls)),
        sources=tuple(dict.fromkeys(source for r in records for source in r.sources)),
    )


def merge(found: Mapping[str, list[Candidate]], limit: int) -> list[Candidate]:
    """One candidate per paper (D73). `found` maps each source to its results, most trusted source first. Papers more
    sources found come first, then the best position any source gave them."""
    # ponytail: a record matching two groups joins the first; merging the groups needs union-find, add it if a
    # search ever shows one paper twice.
    groups: list[list[tuple[int, Candidate]]] = []
    for results in found.values():
        for position, candidate in enumerate(results):
            group = next((g for g in groups if any(_same_paper(candidate, other) for _, other in g)), None)
            if group is None:
                groups.append([(position, candidate)])
            else:
                group.append((position, candidate))
    ranked = sorted(groups, key=lambda g: (-len({s for _, c in g for s in c.sources}), min(p for p, _ in g)))
    return [_combined([candidate for _, candidate in group]) for group in ranked[:limit]]
