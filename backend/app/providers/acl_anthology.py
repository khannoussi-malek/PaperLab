"""ACL Anthology (https://aclanthology.org), harvested from its public metadata dump: one gzip BibTeX file,
anthology+abstracts.bib.gz (~47 MB, ~139k entries, confirmed live 2026-11-13). Nothing here searches the network:
the harvest (workers/harvest.py) downloads the file weekly, and search_page answers Workspace Search from Postgres.

The file carries ETag and Last-Modified (confirmed live), so a conditional GET with If-None-Match answers 304 when
nothing changed. Entries are BibTeX; the citation key is not the Anthology ID, which is the last path segment of the
entry's url (e.g. https://aclanthology.org/2023.acl-long.1). Only inproceedings and article entries are kept (never
proceedings or book entries). Values keep their LaTeX escapes (`{\\v{Z}}`), so they are decoded here, with
pylatexenc, only when they contain a backslash, brace, dollar, tilde, backtick or a double hyphen.
"""

import gzip
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bibtexparser
import httpx
from pylatexenc.latex2text import LatexNodes2Text
from sqlalchemy import and_, or_, select

from app.db import SessionLocal
from app.models import ExternalRef
from app.providers.arxiv import title_words
from app.providers.http import retrying

BASE_URL = "https://aclanthology.org"
DUMP_PATH = "/anthology+abstracts.bib.gz"
TIMEOUT = httpx.Timeout(60.0)  # a read timeout per chunk: the 47 MB download can take a while on a slow link.
# Honest identification, the same as IACR's harvester: a plain User-Agent names the harvester and its project.
_USER_AGENT = "PaperLab/1.0 (+https://github.com/khannoussi-malek/PaperLab; ACL Anthology metadata harvester)"
KEPT_TYPES = frozenset({"inproceedings", "article"})
_ENTRY_START = re.compile(r"^@[A-Za-z]+\s*\{")  # the first line of every entry in the dump
_NEEDS_DECODE = re.compile(r"[\\{}$~`]|--")
_LATEX = LatexNodes2Text()


@dataclass(frozen=True)
class Download:
    etag: str | None
    last_modified: str | None


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # The dump takes neither an email nor a key; both parameters exist only to satisfy the uniform
    # new_client(*, email=None, api_key=None, transport=None) signature every provider shares.
    return httpx.AsyncClient(
        base_url=BASE_URL, timeout=TIMEOUT, transport=retrying(transport), headers={"User-Agent": _USER_AGENT}
    )


async def download(
    http: httpx.AsyncClient, target: Path, *, etag: str | None, last_modified: str | None
) -> Download | None:
    """Streams the dump into `target`. Returns its new validators, or None on 304 (nothing changed: the file is not
    written). Any error status raises httpx.HTTPStatusError, with a message that never embeds the request URL."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    async with http.stream("GET", DUMP_PATH, headers=headers) as response:
        if response.status_code == 304:
            return None
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"ACL Anthology answered HTTP {response.status_code}", request=response.request, response=response
            )
        with target.open("wb") as out:
            async for chunk in response.aiter_bytes():
                out.write(chunk)
        return Download(etag=response.headers.get("etag"), last_modified=response.headers.get("last-modified"))


def _chunks(lines: Iterable[str]) -> Iterator[str]:
    """Whole entries, one at a time, so the dump is never parsed as one 150 MB string."""
    buffer: list[str] = []
    for line in lines:
        if _ENTRY_START.match(line) and buffer:
            yield "".join(buffer)
            buffer = []
        buffer.append(line)
    if buffer:
        yield "".join(buffer)


def _decode(value: str | None) -> str | None:
    if not value:
        return None
    text = _LATEX.latex_to_text(value) if _NEEDS_DECODE.search(value) else value
    return " ".join(text.split()) or None


def _author(name: str) -> str:
    """BibTeX writes "Last, First"; the rest of PaperLab stores "First Last"."""
    if "," in name:
        last, _, first = name.partition(",")
        return f"{first.strip()} {last.strip()}".strip()
    return name


def _authors(raw: str | None) -> list[str]:
    names = (_decode(part) for part in (raw or "").split(" and "))
    return [_author(name) for name in names if name]


def _year(raw: str | None) -> int | None:
    return int(raw) if raw and raw.strip().isdigit() else None


def _entry(entry: Any) -> dict[str, Any] | None:
    """One parsed BibTeX entry as the harvest and the mapper want it, or None when it is not a kept paper."""
    if entry.entry_type.lower() not in KEPT_TYPES:
        return None
    fields = {name: field.value for name, field in entry.fields_dict.items()}
    url = (fields.get("url") or "").strip()
    acl_id = url.rstrip("/").rsplit("/", 1)[-1]
    if not acl_id:
        return None
    return {
        "id": acl_id,
        "title": _decode(fields.get("title")),
        "authors": _authors(fields.get("author")),
        "year": _year(fields.get("year")),
        "venue": _decode(fields.get("booktitle") or fields.get("journal")),
        "doi": (fields.get("doi") or "").strip() or None,
        "abstract": _decode(fields.get("abstract")),
    }


def iter_entries(dump: Path) -> Iterator[dict[str, Any]]:
    """Every kept paper in the gzip dump, parsed one entry at a time."""
    with gzip.open(dump, "rt", encoding="utf-8") as text:
        for chunk in _chunks(text):
            for entry in bibtexparser.parse_string(chunk).entries:
                parsed = _entry(entry)
                if parsed is not None:
                    yield parsed


async def search_page(
    http: httpx.AsyncClient | None, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """Like IACR's search_page: never touches the network (`http` is unused, to match the uniform PageFunc). Words
    are ANDed, each matched in the title or the abstract, case-insensitively. Scoped to this source's own rows by
    the acl_anthology key, so another source's paper never comes back."""
    words = title_words(term)
    if not words:
        return [], None
    async with SessionLocal() as session:
        query = (
            select(ExternalRef)
            .where(ExternalRef.external_ids.has_key("acl_anthology"))
            .where(and_(*(or_(ExternalRef.title.icontains(w, autoescape=True),
                              ExternalRef.abstract.icontains(w, autoescape=True)) for w in words)))
            .order_by(ExternalRef.id)
            .offset(cursor)
            .limit(page_size)
        )  # fmt: skip
        rows = (await session.execute(query)).scalars().all()
        entries = [
            {"id": r.external_ids["acl_anthology"], "title": r.title, "authors": r.authors, "year": r.year,
             "venue": r.venue, "doi": r.doi, "abstract": r.abstract}
            for r in rows
        ]  # fmt: skip
        next_cursor = cursor + page_size if len(rows) == page_size else None
        return entries, next_cursor
