"""Page count, References position and unresolved marks of a compiled PDF (P9). Reads with pymupdf."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:references|bibliography)\s*$", re.I)
_UNRESOLVED = re.compile(r"\?\?|\[\?\]")
_FRESH_PAGE_WORDS = 15  # fewer words than this above the heading: the body ended on the page before
_HEADER_BAND = 0.10  # top fraction of a page skipped when counting words (running headers)
_REPEAT_TOLERANCE = 3.0  # pt: a heading-like line repeated on another page at this y is a running head


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


def _is_running_head(match: tuple[int, float], matches: list[tuple[int, float]]) -> bool:
    """A match repeated at about the same y on another page is a running head, not a heading."""
    page, y0 = match
    return any(
        other != page and abs(y0 - other_y0) <= _REPEAT_TOLERANCE
        for other, other_y0 in matches
    )


def stats(path: Path) -> PdfStats:
    with pymupdf.open(path) as doc:
        pages: list[tuple[list[tuple[float, float, str]], float]] = []  # (lines, top band y) per page
        matches: list[tuple[int, float]] = []  # (0-based page, y0) of every heading-like line
        for index, page in enumerate(doc):
            lines = _lines(page)
            pages.append((lines, _HEADER_BAND * page.rect.height))
            matches += [(index, y0) for y0, _, text in lines if _HEADING.match(text)]
        headings = [m for m in matches if not _is_running_head(m, matches)]
        if not headings:
            return PdfStats(doc.page_count, None)
        # The last real heading is the References heading; a contents page may list it earlier.
        index, heading_y = headings[-1]
        lines, top = pages[index]
        words = sum(
            len(text.split())
            for y0, y1, text in lines
            if y1 < heading_y and y0 > top
        )
        page_no = index + 1
        body = page_no if words >= _FRESH_PAGE_WORDS else page_no - 1
        return PdfStats(doc.page_count, body or None)


def unresolved(path: Path) -> list[tuple[int, int]]:
    """[(1-based page, count)] for pages holding unresolved ?? or [?] marks; pages with none are omitted."""
    with pymupdf.open(path) as doc:
        counts = [(n, len(_UNRESOLVED.findall(page.get_text()))) for n, page in enumerate(doc, start=1)]
    return [(n, c) for n, c in counts if c]
