from collections import Counter
from dataclasses import dataclass
from itertools import takewhile
from pathlib import Path

import pymupdf

from app.core.chunking import Block, join_lines
from app.core.errors import InvalidInput
from app.core.table_grid import CAPTION_GAP, Rect, Word

# No TEXT_PRESERVE_LIGATURES: "ﬁ" must become "fi" or full-text search misses the word.
# (TEXT_DEHYPHENATE has no effect in "dict" mode; join_lines handles hyphenation.)
TEXT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
BOLD_FLAG = 16
HORIZONTAL = (1.0, 0.0)
# ponytail: a scanned PDF often still has a few stray chars (stamps, page numbers).
MIN_CHARS_PER_PAGE = 50


@dataclass(frozen=True)
class ExtractedDoc:
    page_count: int
    title: str | None
    blocks: list[Block]
    # For enrichment: page 1 as plain text (unlike blocks, it keeps rotated text such as the arXiv stamp),
    # and the PDF's embedded metadata (title, author, subject, keywords, creationDate, ...).
    first_page_text: str
    metadata: dict[str, str]


def _block(page_number: int, raw: dict) -> Block | None:
    # Rotated text is margin furniture (e.g. the arXiv sidebar stamp), not content.
    lines = [line for line in raw["lines"] if line["dir"] == HORIZONTAL]
    spans = [s for line in lines for s in line["spans"]]
    text = join_lines(["".join(s["text"] for s in line["spans"]) for line in lines])
    if not text:
        return None
    sizes = Counter()
    bold_chars = 0
    for span in spans:
        sizes[span["size"]] += len(span["text"])
        bold_chars += len(span["text"]) if span["flags"] & BOLD_FLAG else 0
    total = sum(sizes.values()) or 1
    return Block(
        page=page_number,
        bbox=tuple(raw["bbox"]),
        text=text,
        size=sizes.most_common(1)[0][0],
        bold=bold_chars / total > 0.5,
    )


def _title_from_blocks(blocks: list[Block]) -> str | None:
    """The largest text on page 1, continued through the blocks right after it in the same size and weight.

    K1: a centred second title line is its own block. Requiring the same bold flag too keeps a same-size,
    non-bold author line right below the title from being swallowed into it.
    """
    first_page = [b for b in blocks if b.page == 1]
    if not first_page:
        return None
    size = max(b.size for b in first_page)
    start = next(i for i, b in enumerate(first_page) if b.size == size)
    bold = first_page[start].bold
    continued = takewhile(lambda b: b.size == size and b.bold == bold, first_page[start:])
    return join_lines([b.text for b in continued])


def extract(path: str | Path) -> ExtractedDoc:
    """Text blocks with bboxes in PDF points (top-left origin, relative to the crop box).

    ponytail: assumes unrotated pages; apply page.rotation_matrix if rotated scans show up.
    """
    with pymupdf.open(path) as doc:
        blocks = [
            block
            for page in doc
            for raw in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]
            if raw["type"] == 0 and (block := _block(page.number + 1, raw))
        ]
        page_count = doc.page_count
        metadata = {key: value.strip() for key, value in (doc.metadata or {}).items() if isinstance(value, str)}
        first_page_text = doc[0].get_text() if page_count else ""

    if sum(len(b.text) for b in blocks) < MIN_CHARS_PER_PAGE * page_count:
        raise InvalidInput("PDF has no usable text layer (scanned?). Run OCR on it and upload again.")

    return ExtractedDoc(
        page_count=page_count,
        title=metadata.get("title") or _title_from_blocks(blocks),
        blocks=blocks,
        first_page_text=first_page_text,
        metadata=metadata,
    )


@dataclass(frozen=True)
class RegionText:
    words: list[Word]
    # Text blocks around the region (CAPTION_GAP points above and below), where a table's caption sits.
    blocks: list[tuple[Rect, str]]


def read_region(path: str | Path, page_number: int, region: Rect) -> RegionText:
    """The words inside `region` on a 1-based page, in PDF points with a top-left origin, like `extract`."""
    with pymupdf.open(path) as doc:
        # The paper's stored page count can be unknown, so the document bounds the page too.
        if not 1 <= page_number <= doc.page_count:
            raise InvalidInput(f"page {page_number} is outside 1..{doc.page_count}")
        page = doc[page_number - 1]
        words = [Word(*w[:5]) for w in page.get_text("words", clip=pymupdf.Rect(region), flags=TEXT_FLAGS)]
        # Whole blocks, filtered by position: a clip would cut a caption block down to its lines inside the band.
        top, bottom = region[1] - CAPTION_GAP, region[3] + CAPTION_GAP
        blocks = [
            (tuple(b[:4]), b[4])
            for b in page.get_text("blocks", flags=TEXT_FLAGS)
            if b[6] == 0 and b[3] >= top and b[1] <= bottom
        ]
    return RegionText(words=words, blocks=blocks)


def quote_rects(path: str | Path, page_number: int, blocks: list[Rect], quote: str) -> list[Rect]:
    """The quote's line rects on a 1-based page, like a reader's selection, or [] when PyMuPDF doesn't find it there.

    search_for matches loosely (any case, across lines and across paragraphs, anywhere on the page), so only rects
    inside `blocks`, the paragraphs a caller already matched the quote to, count: a caption or another column repeating
    the words is not the passage.
    """
    with pymupdf.open(path) as doc:
        if not 1 <= page_number <= doc.page_count:
            return []
        found = doc[page_number - 1].search_for(" ".join(quote.split()))
    return [tuple(round(v, 2) for v in r) for r in found if any(r.intersects(pymupdf.Rect(b)) for b in blocks)]
