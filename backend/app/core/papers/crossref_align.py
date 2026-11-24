"""Crossref's view of a paper: its work record, bibliographic fields, and whether it lines up with OpenAlex's."""

import html
import re
from typing import Any

import httpx

from app.domain.source_types import is_preprint_copy
from app.models import Paper
from app.providers import crossref


async def _crossref_work(http: httpx.AsyncClient, doi: str, cache: dict[str, dict | None]) -> dict | None:
    """One Crossref fetch per DOI per `cache`; a failed fetch is remembered too, then re-raised."""
    if doi not in cache:
        cache[doi] = None
        cache[doi] = await crossref.get_work(http, doi)
    return cache[doi]


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
