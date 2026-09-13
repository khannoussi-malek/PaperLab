from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.core.chunking import Block, join_lines
from app.core.errors import InvalidInput

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
        meta_title = (doc.metadata or {}).get("title", "").strip()

    if sum(len(b.text) for b in blocks) < MIN_CHARS_PER_PAGE * page_count:
        raise InvalidInput("PDF has no usable text layer (scanned?). Run OCR on it and upload again.")

    first_page = [b for b in blocks if b.page == 1]
    largest = max(first_page, key=lambda b: b.size, default=None)
    return ExtractedDoc(page_count=page_count, title=meta_title or (largest.text if largest else None), blocks=blocks)
