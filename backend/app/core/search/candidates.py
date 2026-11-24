"""Papers found outside the library: one candidate per source record, merged into one list (M19, M19.5).

- PDF URLs: arXiv by ID first, then each record's links in order; landing pages are never listed (D68).
- Merging (D73): records sharing a DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID or CORE ID are one paper, and so
  are records with the same title and a shared author surname. Fields come from the most trusted record that has them.
"""

import re
import unicodedata
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.core.papers.enrichment import ARXIV_DOI_PREFIX, normalize_doi
from app.domain.candidates import MAX_PDF_URLS, Candidate
from app.domain.source_types import PREPRINT_SERVERS

ARXIV_ID = r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7}"
_ARXIV_URL = re.compile(rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})", re.IGNORECASE)
ARXIV_VERSION = re.compile(r"v\d+$")


def arxiv_from_doi(doi: str | None) -> str | None:
    return doi.removeprefix(ARXIV_DOI_PREFIX) if doi and doi.startswith(ARXIV_DOI_PREFIX) else None


def arxiv_from_url(url: str | None) -> str | None:
    match = _ARXIV_URL.search(url or "")
    return match.group(1).lower() if match else None


# Publishers that answer a script with a Cloudflare challenge: tried after every other copy, never skipped.
BOT_CHECKED_HOSTS = ("dl.acm.org", "direct.mit.edu", "www.science.org", "science.org")


def _bot_checked(url: str) -> bool:
    try:
        return urlsplit(url).hostname in BOT_CHECKED_HOSTS
    except ValueError:  # malformed: the download refuses it as unsafe_url
        return False


def ordered_pdf_urls(arxiv_id: str | None, *links: str | None) -> list[str]:
    """arXiv first, then `links` in order with the bot-checked publishers moved last: deduplicated, http(s) only,
    capped at MAX_PDF_URLS (D68)."""
    urls = [f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None, *links]
    deduped = list(dict.fromkeys(url for url in urls if url and url.startswith(("http://", "https://"))))
    return sorted(deduped, key=_bot_checked)[:MAX_PDF_URLS]  # sorted is stable


S2_TYPES = {
    "JournalArticle": "journal_article", "Conference": "proceedings", "Review": "journal_article",
    "Book": "book", "BookSection": "chapter",
}  # fmt: skip


def s2_triage(paper: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(source_type, published_doi, published_venue) from a Semantic Scholar paper. S2 often names the preprint
    server as the "journal" of a JournalArticle: that is no journal. Such a paper is a preprint; an arXiv paper
    that also has a non-arXiv DOI gives that DOI as the published version's."""
    ids = paper.get("externalIds") or {}
    types = paper.get("publicationTypes") or []

    def real(name: str | None) -> str | None:
        return None if not name or PREPRINT_SERVERS.search(name) else name

    journal, venue = (paper.get("journal") or {}).get("name"), paper.get("venue")
    named_server = any(n and PREPRINT_SERVERS.search(n) for n in (journal, venue))
    source_type = next((S2_TYPES[t] for t in types if t in S2_TYPES), None)
    if set(types) <= {"JournalArticle"} and not real(journal) and (named_server or ids.get("ArXiv")):
        source_type = "preprint"
    doi = normalize_doi(ids.get("DOI") or "") if ids.get("ArXiv") else None
    if doi and doi.startswith(ARXIV_DOI_PREFIX):
        doi = None
    return source_type, doi, None if source_type == "preprint" else real(journal) or real(venue)


def arxiv_triage(entry: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(source_type, published_doi, published_venue) from an arXiv entry: a journal_ref means it was published."""
    journal_ref = (entry.get("journal_ref") or "").strip() or None
    if not journal_ref:
        return "preprint", None, None
    doi = normalize_doi(entry.get("doi") or "")
    return "journal_article", None if doi and doi.startswith(ARXIV_DOI_PREFIX) else doi, journal_ref


def normal_title(title: str) -> str:
    return re.sub(r"\W+", " ", title).strip().casefold()


def surname(name: str) -> str:
    """ "Uszkoreit, Jakob" and "Jakob Uszkoreit" both give "uszkoreit"; accents are dropped ("Krönke" → "kronke")."""
    part = name.split(",")[0] if "," in name else next(reversed(name.split()), "")
    return "".join(c for c in unicodedata.normalize("NFKD", part) if not unicodedata.combining(c)).strip().casefold()


def _ids(candidate: Candidate) -> set[str]:
    # ponytail: hardcodes today's id kinds — can't derive this list from source_registry (it imports
    # *from* this module, so importing it back would be circular). Add one line here per future source;
    # restructure only if that becomes its own recurring chore across several sources at once.
    arxiv_id = candidate.external_ids.get("arxiv") or arxiv_from_doi(candidate.doi)
    keys = {
        "doi": None if arxiv_from_doi(candidate.doi) else candidate.doi,
        "arxiv": arxiv_id,
        "openalex": candidate.external_ids.get("openalex"),
        "s2": candidate.external_ids.get("semantic_scholar"),
        "core": candidate.external_ids.get("core"),
        "pubmed": candidate.external_ids.get("pubmed"),
        "pmc": candidate.external_ids.get("pmc"),
        "zenodo": candidate.external_ids.get("zenodo"),
        "hal": candidate.external_ids.get("hal"),
        "doaj": candidate.external_ids.get("doaj"),
        "openaire": candidate.external_ids.get("openaire"),
        "openreview": candidate.external_ids.get("openreview"),
        "acl_anthology": candidate.external_ids.get("acl_anthology"),
        "iacr_eprint": candidate.external_ids.get("iacr_eprint"),
        "biorxiv": candidate.external_ids.get("biorxiv"),
        "medrxiv": candidate.external_ids.get("medrxiv"),
        "dblp": candidate.external_ids.get("dblp"),
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

    def first_id(source: str) -> str | None:
        return next((value for r in records if (value := r.external_ids.get(source))), None)

    arxiv_id = first_id("arxiv")
    external_ids = {
        k: v
        for k, v in {
            "dblp": first_id("dblp"),
            "arxiv": arxiv_id, "openalex": first_id("openalex"), "semantic_scholar": first_id("semantic_scholar"),
            "core": first_id("core"), "pubmed": first_id("pubmed"), "pmc": first_id("pmc"),
            "zenodo": first_id("zenodo"), "hal": first_id("hal"), "doaj": first_id("doaj"),
            "openaire": first_id("openaire"), "openreview": first_id("openreview"),
            "acl_anthology": first_id("acl_anthology"),
            "iacr_eprint": first_id("iacr_eprint"),
            "biorxiv": first_id("biorxiv"), "medrxiv": first_id("medrxiv"),
        }.items()
        if v
    }
    counts = [r.cited_by_count for r in records if r.cited_by_count is not None]
    return Candidate(
        title=records[0].title,
        authors=first("authors") or [],
        year=first("year"),
        venue=first("venue"),
        doi=first("doi"),
        external_ids=external_ids,
        cited_by_count=max(counts, default=None),
        abstract=first("abstract"),
        pdf_urls=ordered_pdf_urls(arxiv_id, *(url for r in records for url in r.pdf_urls)),
        sources=tuple(dict.fromkeys(source for r in records for source in r.sources)),
        source_type=first("source_type"),
        published_doi=first("published_doi"),
        published_venue=first("published_venue"),
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
