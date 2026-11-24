"""Candidates from repositories' and preprint servers' records: Zenodo, HAL, ACM DL, SSRN, DOAJ, OpenAIRE,
OpenReview, IACR ePrint, the ACL Anthology, bioRxiv and medRxiv."""

import html
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from app.core.search.candidates import arxiv_from_doi, ordered_pdf_urls
from app.core.search.from_indexes import from_crossref, from_work
from app.domain.candidates import MAX_AUTHORS, Candidate


def from_zenodo(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/zenodo.py. Direct PDF links are real (confirmed live 2026-10-09), unlike
    Europe PMC's own equivalent claim, which turned out to be Cloudflare-blocked."""
    doi = entry.get("doi")
    arxiv_id = arxiv_from_doi(doi)
    external_ids = {k: v for k, v in {"zenodo": entry["id"], "arxiv": arxiv_id}.items() if v}
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=doi,
        external_ids=external_ids,
        abstract=entry.get("abstract"),
        pdf_urls=ordered_pdf_urls(arxiv_id, entry.get("pdf_url")),
        sources=("zenodo",),
    )


def from_hal(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/hal.py. Direct PDF links are real (confirmed live 2026-10-09) but not
    every record has a file -- hal.py's own entry["pdf_url"] is already None when absent."""
    doi = entry.get("doi")
    arxiv_id = arxiv_from_doi(doi)
    external_ids = {k: v for k, v in {"hal": str(entry["docid"]), "arxiv": arxiv_id}.items() if v}
    return Candidate(
        title=entry["title"] or "Untitled",
        authors=list(entry["authors"])[:MAX_AUTHORS],
        year=entry["year"],
        doi=doi,
        external_ids=external_ids,
        abstract=entry.get("abstract"),
        pdf_urls=ordered_pdf_urls(arxiv_id, entry.get("pdf_url")),
        sources=("hal",),
    )


def from_acm_dl(item: Mapping[str, Any]) -> Candidate | None:
    """ACM DL records, found via Crossref filtered to the 10.1145 DOI prefix (confirmed live to be solely
    ACM's own). An ACM DL record IS a Crossref record -- just a narrower slice of the same data -- so
    this reuses from_crossref's own type filter, field reading and "no PDF" rule verbatim; only the
    sources tag differs."""
    candidate = from_crossref(item)
    return replace(candidate, sources=("acm_dl",)) if candidate else None


def from_ssrn(work: Mapping[str, Any]) -> Candidate:
    """SSRN records, found via OpenAlex filtered to its own SSRN source id (confirmed live). An SSRN
    record IS an OpenAlex work -- just a narrower slice of the same data -- so this reuses from_work's
    own field reading verbatim; only the sources tag differs. OpenAlex's pdf_url fields are consistently
    null for SSRN even when flagged open-access (confirmed live, 2026-10-10): only a landing-page link is
    ever present, and from_work already never reads that field, so pdf_urls comes back empty here with no
    extra code."""
    return replace(from_work(work), sources=("ssrn",))


_TAG = re.compile(r"</?[A-Za-z][\w:-]*(?:\s[^<>]*)?/?>")


def _clean_markup(text: str | None) -> str | None:
    """Strips HTML/JATS tags and unescapes entities, the same pattern zenodo.py's and europe_pmc.py's own
    private _clean() already use -- DOAJ and OpenAIRE both confirmed live to carry raw markup in their
    abstract text (ponytail: a fourth near-identical copy; extract a shared helper if a fifth source ever
    needs this too, not before)."""
    cleaned = " ".join(_TAG.sub("", html.unescape(text or "")).split())
    return cleaned or None


def from_doaj(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/doaj.py. Not every article carries a DOI (confirmed live: some only have
    an ISSN) -- doaj's own native id becomes this source's own external_ids key. Only a link whose
    content_type is "pdf" (case-insensitive) counts as a real PDF; DOAJ's own content_type field is
    otherwise messy and inconsistent (confirmed live), and an HTML landing-page link must never be
    mistaken for one."""
    bibjson = entry.get("bibjson") or {}
    doi = next(
        (ident["id"].lower() for ident in bibjson.get("identifier") or [] if ident.get("type") == "doi"), None
    )
    arxiv_id = arxiv_from_doi(doi)
    pdf_url = next(
        (link["url"] for link in bibjson.get("link") or [] if (link.get("content_type") or "").lower() == "pdf"),
        None,
    )
    year_str = bibjson.get("year") or ""
    return Candidate(
        title=bibjson.get("title") or "Untitled",
        authors=[a["name"] for a in bibjson.get("author") or [] if a.get("name")][:MAX_AUTHORS],
        year=int(year_str) if year_str.isdigit() else None,
        doi=doi,
        external_ids={"doaj": entry["id"]},
        abstract=_clean_markup(bibjson.get("abstract")),
        pdf_urls=ordered_pdf_urls(arxiv_id, pdf_url),
        sources=("doaj",),
    )


def from_openaire(entry: Mapping[str, Any]) -> Candidate | None:
    """An entry from providers/openaire.py. None for a record that isn't a publication -- search()/
    search_page() already send type=publication on every request (Review Focus #3), so this is defense
    in depth for the rare record that slips through anyway, the same role from_crossref's own type
    filter plays for ACM DL. Never a PDF: instances[].urls are DOI-resolver landing-page links,
    confirmed live to never be a direct file, matching crossref.py's own "no PDF" rule. OpenAIRE's own
    native id (a "<tag>::<32-hex>" string) becomes this source's own external_ids key."""
    if entry.get("type") != "publication":
        return None
    doi = next((pid["value"].lower() for pid in entry.get("pids") or [] if pid.get("scheme") == "doi"), None)
    arxiv_id = arxiv_from_doi(doi)
    descriptions = entry.get("descriptions") or []
    pub_date = entry.get("publicationDate") or ""
    year = int(pub_date[:4]) if pub_date[:4].isdigit() else None
    return Candidate(
        title=entry.get("mainTitle") or "Untitled",
        authors=[a["fullName"] for a in entry.get("authors") or [] if a.get("fullName")][:MAX_AUTHORS],
        year=year,
        doi=doi,
        external_ids={"openaire": entry["id"]},
        abstract=_clean_markup(descriptions[0]) if descriptions else None,
        pdf_urls=ordered_pdf_urls(arxiv_id),
        sources=("openaire",),
    )


OPENREVIEW_SITE = "https://openreview.net"
OPENREVIEW_SUBMISSION_SUFFIXES = ("/-/Submission", "/-/Blind_Submission")


def _openreview_value(field: Any) -> Any:
    """API v2 wraps each content value in {"value": ...}; a plain value (the older shape) passes through."""
    return field.get("value") if isinstance(field, Mapping) else field


def _is_openreview_submission(entry: Mapping[str, Any], venue_id: Any) -> bool:
    """Reviews, comments and decisions share the search endpoint: keep a note only when its invitation is a
    submission's. A note with no invitations at all is kept when it carries a venue id."""
    invitations = entry.get("invitations") or []
    if invitations:
        return any(str(invitation).endswith(OPENREVIEW_SUBMISSION_SUFFIXES) for invitation in invitations)
    return bool(venue_id)


def from_openreview(entry: Mapping[str, Any]) -> Candidate | None:
    """An entry from providers/openreview.py. None for a note that isn't a submission (reviews, comments and
    decisions are dropped here), or one with no title or forum id. Blind submissions have no authors, so the list
    is empty. The PDF is OpenReview's own /pdf/ link, made absolute. `cdate` is milliseconds since the epoch, read in
    UTC for the year."""
    content = entry.get("content") or {}
    title = _openreview_value(content.get("title"))
    forum = entry.get("forum")
    if not title or not forum or not _is_openreview_submission(entry, _openreview_value(content.get("venueid"))):
        return None
    authors = _openreview_value(content.get("authors"))
    cdate = entry.get("cdate")
    pdf = _openreview_value(content.get("pdf"))
    return Candidate(
        title=title,
        authors=[a for a in authors if isinstance(a, str)][:MAX_AUTHORS] if isinstance(authors, list) else [],
        year=datetime.fromtimestamp(cdate / 1000, tz=UTC).year if isinstance(cdate, int | float) else None,
        venue=_openreview_value(content.get("venue")) or None,
        external_ids={"openreview": forum},
        abstract=_clean_markup(_openreview_value(content.get("abstract"))),
        pdf_urls=ordered_pdf_urls(None, urljoin(OPENREVIEW_SITE, pdf) if pdf else None),
        sources=("openreview",),
    )


def from_iacr_eprint(entry: Mapping[str, Any]) -> Candidate:
    """An entry from providers/iacr_eprint.py's own fetch_page(). The bare eprint id (e.g. "2026/2368")
    is extracted from the OAI identifier ("oai:eprint.iacr.org:2026/2368") and becomes this source's own
    external_ids key -- most eprints have no DOI at all. `year` comes from the id's own 4-digit year
    prefix, not the OAI `datestamp` -- confirmed live, `datestamp` is the record's last-MODIFIED time, so
    a revised eprint's datestamp can land a year after its actual publication year (roughly a quarter of
    real harvested records). The id's year prefix is always present and always valid: the id format is
    already enforced elsewhere as ^\\d{4}/\\d{1,6}$. Never a PDF: constructing one
    (https://eprint.iacr.org/<id>.pdf) is deliberately not attempted here; this plan's own scope is
    getting IACR searchable, not fetching its files."""
    eprint_id = entry["identifier"].removeprefix("oai:eprint.iacr.org:")
    return Candidate(
        title=entry.get("title") or "Untitled",
        authors=list(entry.get("creators") or [])[:MAX_AUTHORS],
        year=int(eprint_id[:4]) if eprint_id[:4].isdigit() else None,
        external_ids={"iacr_eprint": eprint_id},
        abstract=entry.get("description") or None,
        sources=("iacr_eprint",),
    )


def from_acl_anthology(entry: Mapping[str, Any]) -> Candidate:
    """A paper from providers/acl_anthology.py: the Anthology ID (e.g. "2023.acl-long.1") is this source's own key,
    and the PDF is the Anthology's own convention, https://aclanthology.org/<id>.pdf. The file has no abstract or DOI
    for some entries, so those stay None. Whether a row is a paper at all is decided before this mapper runs."""
    acl_id = entry["id"]
    return Candidate(
        title=entry.get("title") or "Untitled",
        authors=list(entry.get("authors") or [])[:MAX_AUTHORS],
        year=entry.get("year"),
        venue=entry.get("venue") or None,
        doi=entry.get("doi") or None,
        external_ids={"acl_anthology": acl_id},
        abstract=entry.get("abstract") or None,
        pdf_urls=ordered_pdf_urls(None, f"https://aclanthology.org/{acl_id}.pdf"),
        sources=("acl_anthology",),
    )


def from_biorxiv_entry(entry: Mapping[str, Any], *, server: str) -> Candidate:
    """An entry from providers/biorxiv.py's own fetch_page() 'collection' list, for either server
    ("biorxiv" or "medrxiv") -- the real API's own response shape is identical between the two, only
    values differ. The DOI (confirmed live, present on virtually every real record -- unlike IACR eprints,
    which mostly have none) becomes both Candidate.doi (the universal field) AND this source's own
    external_ids key, the same value in both places: bioRxiv/medRxiv preprints have no other native id, so
    the external_ids entry exists purely so harvest_ingest_candidate's own find-by-source-key lookup and
    search_page's own per-server isolation filter have something to key on. `authors` is a single "; "-joined
    string in the real API ("Last, F.; Last2, F2."), confirmed live -- split and stripped. `date` is the
    record's own real publication date (confirmed live: unlike IACR's OAI datestamp, which is last-MODIFIED,
    this is the preprint's own posting date), so year comes directly from it, no id-prefix workaround needed.
    Never a PDF: this plan's own scope is getting these two sources searchable, not fetching their files."""
    doi = entry["doi"]
    authors = [name.strip() for name in (entry.get("authors") or "").split(";") if name.strip()]
    date = entry.get("date") or ""
    return Candidate(
        title=entry.get("title") or "Untitled",
        authors=authors[:MAX_AUTHORS],
        year=int(date[:4]) if date[:4].isdigit() else None,
        doi=doi,
        external_ids={server: doi},
        abstract=entry.get("abstract") or None,
        sources=(server,),
    )


def from_biorxiv(entry: Mapping[str, Any]) -> Candidate:
    """Single-arg wrapper around from_biorxiv_entry for the registry's own Mapper slot
    (Callable[[Any], Candidate | None], no room for a server argument)."""
    return from_biorxiv_entry(entry, server="biorxiv")


def from_medrxiv(entry: Mapping[str, Any]) -> Candidate:
    """Single-arg wrapper around from_biorxiv_entry for the registry's own Mapper slot."""
    return from_biorxiv_entry(entry, server="medrxiv")
