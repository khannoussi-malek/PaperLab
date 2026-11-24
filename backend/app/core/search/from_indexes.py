"""Candidates from the big indexes' records: OpenAlex, Semantic Scholar, DBLP, arXiv, Crossref, CORE and the PubMed family."""

import html
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from app.core.papers.enrichment import abstract_text, normalize_doi, short_id
from app.core.search.candidates import (
    ARXIV_VERSION,
    arxiv_from_doi,
    arxiv_from_url,
    arxiv_triage,
    ordered_pdf_urls,
    s2_triage,
)
from app.domain.candidates import MAX_AUTHORS, Candidate
from app.domain.source_types import PREPRINT_SERVERS, source_type_of

# Crossref's title search also returns songs, datasets and peer reviews ("All You Need Is LSD" is type "other").
CROSSREF_PAPER_TYPES = frozenset(
    {"journal-article", "proceedings-article", "posted-content", "book-chapter", "book", "monograph", "report",
     "dissertation"}
)  # fmt: skip


def from_work(work: dict[str, Any]) -> Candidate:
    doi = normalize_doi(work.get("doi") or "")
    best = work.get("best_oa_location") or {}
    locations = work.get("locations") or []
    location_urls = [
        url for place in [best, *locations] for url in (place.get("landing_page_url"), place.get("pdf_url"))
    ]
    arxiv_id = arxiv_from_doi(doi) or next(filter(None, map(arxiv_from_url, location_urls)), None)
    source = (work.get("primary_location") or {}).get("source") or {}
    authors = [a["author"]["display_name"] for a in work.get("authorships") or [] if a.get("author")]
    external_ids = {k: v for k, v in {"openalex": short_id(work.get("id")), "arxiv": arxiv_id}.items() if v}
    source_type = source_type_of(work.get("type"), doi)
    if PREPRINT_SERVERS.search(source.get("display_name") or ""):
        source_type = "preprint"  # hosted on a preprint server, whatever OpenAlex's type says
    return Candidate(
        title=work.get("title") or "Untitled",
        authors=authors[:MAX_AUTHORS],
        year=work.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi,
        external_ids=external_ids,
        cited_by_count=work.get("cited_by_count"),
        abstract=abstract_text(work.get("abstract_inverted_index")),
        pdf_urls=ordered_pdf_urls(arxiv_id, best.get("pdf_url"), *(place.get("pdf_url") for place in locations)),
        sources=("openalex",),
        source_type=source_type,
        published_venue=None if source_type == "preprint" else source.get("display_name"),
    )


def from_s2(paper: dict[str, Any]) -> Candidate:
    ids = paper.get("externalIds") or {}
    doi = (ids.get("DOI") or "").lower() or None
    arxiv_id = (ids.get("ArXiv") or "").lower() or arxiv_from_doi(doi)
    external_ids = {k: v for k, v in {"semantic_scholar": paper.get("paperId"), "arxiv": arxiv_id}.items() if v}
    source_type, published_doi, published_venue = s2_triage(paper)
    return Candidate(
        title=paper.get("title") or "Untitled",
        authors=[a["name"] for a in paper.get("authors") or [] if a.get("name")][:MAX_AUTHORS],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        doi=doi,
        external_ids=external_ids,
        cited_by_count=paper.get("citationCount"),
        abstract=paper.get("abstract") or None,
        pdf_urls=ordered_pdf_urls(arxiv_id, (paper.get("openAccessPdf") or {}).get("url")),
        sources=("semantic_scholar",),
        source_type=source_type,
        published_doi=published_doi,
        published_venue=published_venue,
    )


def with_s2(candidate: Candidate, paper: dict[str, Any] | None) -> Candidate:
    """A candidate with Semantic Scholar's arXiv ID and free PDF link added (D70). A lookup, so no new source."""
    if paper is None:
        return candidate
    found = from_s2(paper)
    arxiv_id = candidate.external_ids.get("arxiv") or found.external_ids.get("arxiv")
    external_ids = {**candidate.external_ids, "semantic_scholar": found.external_ids.get("semantic_scholar")}
    if arxiv_id:
        external_ids["arxiv"] = arxiv_id
    return replace(
        candidate,
        external_ids={k: v for k, v in external_ids.items() if v},
        pdf_urls=ordered_pdf_urls(arxiv_id, *found.pdf_urls, *candidate.pdf_urls),
    )


def from_dblp(entry: Mapping[str, Any]) -> Candidate:
    """DBLP supplies metadata and landing pages, never PDF links."""
    authors = (entry.get("authors") or {}).get("author") or []
    if not isinstance(authors, list):
        authors = [authors]
    names = [a.get("text", "") if isinstance(a, dict) else a for a in authors]
    venue = entry.get("venue") or None
    if isinstance(venue, list):
        venue = venue[0] if venue else None
    year = str(entry.get("year") or "")
    doi = (entry.get("doi") or "").removeprefix("https://doi.org/").strip().lower() or None
    links = entry.get("ee") or []
    if not isinstance(links, list):
        links = [links]
    arxiv_id = arxiv_from_doi(doi) or next(
        (found for link in links if isinstance(link, str) and (found := arxiv_from_url(link))), None
    )
    arxiv_id = ARXIV_VERSION.sub("", arxiv_id) if arxiv_id else None
    ids = {k: v for k, v in {"dblp": entry.get("key"), "arxiv": arxiv_id}.items() if v}
    return Candidate(
        title=html.unescape(entry.get("title") or "Untitled").rstrip("."),
        authors=[re.sub(r"\s\d{4}$", "", html.unescape(n)) for n in names if isinstance(n, str) and n][:MAX_AUTHORS],
        year=int(year) if year.isdigit() and len(year) == 4 else None,
        venue=venue, doi=doi, external_ids=ids,
        pdf_urls=ordered_pdf_urls(arxiv_id), sources=("dblp",),
        source_type={
            "Informal and Other Publications": "preprint",
            "Conference and Workshop Papers": "proceedings",
            "Journal Articles": "journal_article",
        }.get(entry.get("type")),
    )


def from_arxiv(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/arxiv.py: its arXiv ID already has no version, and is always present (a parsed
    entry with no id is filtered out by providers/arxiv.py's own _entry())."""
    source_type, published_doi, published_venue = arxiv_triage(entry)
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=entry["doi"],
        external_ids={"arxiv": entry["arxiv_id"]},
        abstract=entry.get("abstract"),
        pdf_urls=ordered_pdf_urls(entry["arxiv_id"]),
        sources=("arxiv",),
        source_type=source_type,
        published_doi=published_doi,
        published_venue=published_venue,
    )


def from_crossref(item: Mapping[str, Any]) -> Candidate | None:
    """None for a record that isn't a paper. Crossref lists no free PDFs: its links are for text mining (D68).
    No abstract either: Crossref's `abstract` field, when present, is raw JATS XML markup, not plain text —
    left unset here rather than surfacing tags to the reader."""
    if item.get("type") not in CROSSREF_PAPER_TYPES:
        return None
    doi = (item.get("DOI") or "").lower() or None
    names = [
        " ".join(filter(None, (a.get("given"), a.get("family")))) or a.get("name") for a in item.get("author") or []
    ]
    [year, *_] = ((item.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    arxiv_id = arxiv_from_doi(doi)
    venue = next(iter(item.get("container-title") or []), None)
    source_type = source_type_of(item.get("type"), doi, crossref=True)
    return Candidate(
        title=next(iter(item.get("title") or []), None) or "Untitled",
        authors=[name for name in names if name][:MAX_AUTHORS],
        year=year,
        venue=venue,
        doi=doi,
        external_ids={"arxiv": arxiv_id} if arxiv_id else {},
        cited_by_count=item.get("is-referenced-by-count"),
        pdf_urls=ordered_pdf_urls(arxiv_id),
        sources=("crossref",),
        source_type=source_type,
        published_venue=None if source_type == "preprint" else venue,
    )


def from_core(work: Mapping[str, Any]) -> Candidate:
    """Only `downloadUrl` is a PDF link: CORE's other full-text URLs include landing pages (D68). Its citation count
    is left out, since CORE counted 0 for a paper cited 100,000 times."""
    doi = (work.get("doi") or "").lower() or None
    arxiv_id = ARXIV_VERSION.sub("", (work.get("arxivId") or "").lower()) or arxiv_from_doi(doi)
    core_id = str(work["id"]) if work.get("id") is not None else None
    external_ids = {k: v for k, v in {"arxiv": arxiv_id, "core": core_id}.items() if v}
    return Candidate(
        title=" ".join((work.get("title") or "").split()) or "Untitled",
        authors=[a["name"] for a in work.get("authors") or [] if a.get("name")][:MAX_AUTHORS],
        year=work.get("yearPublished"),
        doi=doi,
        external_ids=external_ids,
        abstract=work.get("abstract") or None,
        pdf_urls=ordered_pdf_urls(arxiv_id, work.get("downloadUrl")),
        sources=("core",),
    )


def from_pubmed(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/pubmed.py. PubMed never lists a free PDF (PMC's own job, a later milestone)
    and never a citation count (not a MEDLINE field)."""
    doi = entry.get("doi")
    arxiv_id = arxiv_from_doi(doi)
    external_ids = {k: v for k, v in {"pubmed": entry["pmid"], "arxiv": arxiv_id}.items() if v}
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=doi,
        external_ids=external_ids,
        abstract=entry.get("abstract"),
        pdf_urls=ordered_pdf_urls(arxiv_id),
        sources=("pubmed",),
    )


def from_pmc(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/pmc.py. No free PDF: PMC's own OA Web Service that used to provide one is
    confirmed shut down, and the obvious constructed path is a JS proof-of-work interstitial, not a file
    (probed live 2026-10-09)."""
    doi = entry.get("doi")
    arxiv_id = arxiv_from_doi(doi)
    external_ids = {
        k: v for k, v in {"pmc": entry["pmcid"], "pubmed": entry.get("pmid"), "arxiv": arxiv_id}.items() if v
    }
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=doi,
        external_ids=external_ids,
        abstract=entry.get("abstract"),
        sources=("pmc",),
    )


def from_europe_pmc(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/europe_pmc.py. Reuses PubMed's and PMC's own external_ids keys ("pubmed",
    "pmc") rather than inventing a third "europe_pmc" id kind -- Europe PMC never natively owns an
    identifier, it aggregates records PubMed/PMC already key, so a paper it finds dedupes against the
    same paper found via PubMed or PMC automatically, with no extra matching code. No free PDF: the
    website's own direct PDF link is confirmed behind a Cloudflare bot challenge on every probe
    (2026-10-09), not a file this module can reliably fetch."""
    doi = entry.get("doi")
    arxiv_id = arxiv_from_doi(doi)
    external_ids = {
        k: v for k, v in {"pubmed": entry.get("pmid"), "pmc": entry.get("pmcid"), "arxiv": arxiv_id}.items() if v
    }
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=doi,
        external_ids=external_ids,
        cited_by_count=entry.get("cited_by_count"),
        abstract=entry.get("abstract"),
        sources=("europe_pmc",),
    )
