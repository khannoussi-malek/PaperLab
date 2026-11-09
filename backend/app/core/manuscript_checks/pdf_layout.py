"""Page count, References position and unresolved marks of a compiled PDF (P9). Reads with pymupdf."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:references|bibliography)\s*$", re.I)
_UNRESOLVED = re.compile(r"\?\?|\[\?\]")
_FRESH_PAGE_WORDS = 15  # fewer words than this above the heading: the body ended on the page before
_HEADER_BAND = 0.10  # top fraction of a page skipped when counting words (running headers)


@dataclass(frozen=True)
class PdfStats:
    page_count: int
    body_pages: int | None  # None: no References heading found, or it sits on page 1 with no body above it


def _lines(page: pymupdf.Page) -> list[tuple[float, float, str]]:
    """(y0, y1, text) per text line, spans joined."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                _, y0, _, y1 = line["bbox"]
                out.append((y0, y1, text))
    return out


def stats(path: Path) -> PdfStats:
    with pymupdf.open(path) as doc:
        # Keep the last heading match: a contents page may list "References" early.
        last_page, last_heading, last_lines = None, None, []
        for page_no, page in enumerate(doc, start=1):
            lines = _lines(page)
            for y0, _, text in lines:
                if _HEADING.match(text):
                    last_page, last_heading, last_lines = page_no, y0, lines
        if last_page is None:
            return PdfStats(doc.page_count, None)
        top = _HEADER_BAND * doc[last_page - 1].rect.height
        words = sum(
            len(text.split())
            for y0, y1, text in last_lines
            if y1 < last_heading and y0 > top
        )
        body = last_page if words >= _FRESH_PAGE_WORDS else last_page - 1
        return PdfStats(doc.page_count, body or None)


def unresolved(path: Path) -> list[tuple[int, int]]:
    """[(1-based page, count)] for pages holding unresolved ?? or [?] marks; pages with none are omitted."""
    with pymupdf.open(path) as doc:
        counts = [(n, len(_UNRESOLVED.findall(page.get_text()))) for n, page in enumerate(doc, start=1)]
    return [(n, c) for n, c in counts if c]
