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


def _lines(page: pymupdf.Page) -> list[tuple[float, float, float, float, str]]:
    """(x0, y0, x1, y1, text) per text line, spans joined."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, y0, x1, y1 = line["bbox"]
                out.append((x0, y0, x1, y1, text))
    return out


def _is_running_head(match: tuple[int, float, float], matches: list[tuple[int, float, float]]) -> bool:
    """A match repeated at about the same y on another page is a running head, not a heading."""
    page, y0, _ = match
    return any(
        other != page and abs(y0 - other_y0) <= _REPEAT_TOLERANCE
        for other, other_y0, _ in matches
    )


def _body_words(
    lines: list[tuple[float, float, float, float, str]], top: float, heading: tuple[float, float], mid: float
) -> int:
    """Words in the body on the heading's page. A heading that starts the right column also counts the left column."""
    heading_y, heading_x0 = heading
    right_column = heading_x0 > mid
    return sum(
        len(text.split())
        for x0, y0, x1, y1, text in lines
        if y0 > top and (y1 < heading_y or (right_column and x1 <= mid))
    )


def _real_headings(
    candidates: list[tuple[int, float, float]], tops: list[float]
) -> list[tuple[int, float, float]]:
    """If any candidate lies below its page's top band, drop the ones inside the band."""
    # ponytail: a heading at the very top margin plus a running head on just one following page
    # still counts one page too many. Upgrade path: also compare font size.
    below = [m for m in candidates if m[1] > tops[m[0]]]
    return below or candidates


def stats(path: Path) -> PdfStats:
    with pymupdf.open(path) as doc:
        # (lines, top band y, mid x) per page
        pages: list[tuple[list[tuple[float, float, float, float, str]], float, float]] = []
        matches: list[tuple[int, float, float]] = []  # (0-based page, y0, x0) of every heading-like line
        for index, page in enumerate(doc):
            lines = _lines(page)
            pages.append((lines, _HEADER_BAND * page.rect.height, page.rect.width / 2))
            matches += [(index, y0, x0) for x0, y0, _, _, text in lines if _HEADING.match(text)]
        candidates = [m for m in matches if not _is_running_head(m, matches)]
        headings = _real_headings(candidates, [top for _, top, _ in pages])
        if not headings:
            return PdfStats(doc.page_count, None)
        # The last real heading is the References heading; a contents page may list it earlier.
        index, heading_y, heading_x0 = headings[-1]
        lines, top, mid = pages[index]
        words = _body_words(lines, top, (heading_y, heading_x0), mid)
        page_no = index + 1
        body = page_no if words >= _FRESH_PAGE_WORDS else page_no - 1
        return PdfStats(doc.page_count, body or None)


def unresolved(path: Path) -> list[tuple[int, int]]:
    """[(1-based page, count)] for pages holding unresolved ?? or [?] marks; pages with none are omitted."""
    with pymupdf.open(path) as doc:
        counts = [(n, len(_UNRESOLVED.findall(page.get_text()))) for n, page in enumerate(doc, start=1)]
    return [(n, c) for n, c in counts if c]
