"""Block -> chunk conversion. Pure functions, no I/O.

Chunks never cross a page boundary, and each chunk keeps one rect per source block
(PDF points, top-left origin) so citations highlight exactly the text used, even
when a chunk spans two columns.
"""

import re
from collections import Counter
from dataclasses import dataclass, replace

STRATEGY_VERSION = 2  # v2: a block over BLOCK_CAP is split, and a table stays together
MAX_CHARS = 1500
# A block longer than this is split. Embedding memory grows with a text's length squared: the longest real chunks
# (8,181 characters) peak at 1.55 GB, and 30,000 characters ran out of a 2.5 GB cap (measured 2026-11-04). Below it a
# block stays whole, however far past MAX_CHARS: splitting there lost answers further down the results.
BLOCK_CAP = 8000
# Drops figure labels, footnotes, and page furniture; keeps table text (~9pt vs ~11pt body).
MIN_SIZE_RATIO = 0.75
HEADING_MAX_CHARS = 90
# ponytail: drops figure labels and page numbers by word count. Figure text of 4+ words at
# body size still slips through; upgrade path is skipping blocks inside page.get_drawings() regions.
MIN_WORDS = 4
# Overlap is only used when no headings are found; big blocks aren't worth repeating.
OVERLAP_MAX_CHARS = MAX_CHARS // 3

_HAS_LETTER = re.compile(r"[A-Za-z]")

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class Block:
    page: int  # 1-based, matching PDF.js
    bbox: Rect
    text: str
    size: float  # dominant font size, weighted by characters
    bold: bool
    table: int | None = None  # which table of the document it sits in


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    page: int
    bbox: list[list[float]]
    section_title: str | None
    text: str


def join_lines(lines: list[str]) -> str:
    """Join PDF lines, rejoining words hyphenated across a line break ("trans-" + "fer")."""
    text = ""
    for line in filter(None, (raw.strip() for raw in lines)):
        if text.endswith("-") and text[-2:-1].isalpha() and line[0].islower():
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return text


def body_font_size(blocks: list[Block]) -> float:
    sizes = Counter()
    for block in blocks:
        sizes[round(block.size, 1)] += len(block.text)
    return sizes.most_common(1)[0][0] if sizes else 0.0


def is_heading(block: Block, body_size: float) -> bool:
    # ponytail: font heuristic, misses wrapped two-line headings and unstyled ones.
    # Upgrade path: PDF outline (doc.get_toc()) when present, before this fallback.
    x0, y0, x1, y1 = block.bbox
    single_line = (y1 - y0) <= 2 * block.size
    return (
        len(block.text) <= HEADING_MAX_CHARS
        and single_line
        and block.size >= body_size - 0.2
        and (block.bold or block.size >= body_size + 1)
        and bool(_HAS_LETTER.search(block.text))
    )


def _draft(ordinal: int, blocks: list[Block], section: str | None) -> ChunkDraft:
    return ChunkDraft(
        ordinal=ordinal,
        page=blocks[0].page,
        bbox=[[round(v, 2) for v in b.bbox] for b in blocks],
        section_title=section,
        text="\n\n".join(b.text for b in blocks),
    )


def _pieces(block: Block) -> list[Block]:
    """The block itself when it fits (heading ids depend on it), else cut at the last sentence end, else the last space,
    else hard.
    ponytail: every piece keeps the whole block's rect, so a citation highlights the block; per-line rects are the
    upgrade."""
    pieces, rest = [], block.text
    while len(rest) > BLOCK_CAP:
        window = rest[:BLOCK_CAP]
        cut = window.rfind(". ") + 1 or window.rfind(" ") + 1 or BLOCK_CAP
        pieces.append(replace(block, text=rest[:cut].strip()))
        rest = rest[cut:].strip()
    return [*pieces, replace(block, text=rest)] if pieces else [block]


def chunk_blocks(blocks: list[Block], max_chars: int = MAX_CHARS) -> list[ChunkDraft]:
    body_size = body_font_size(blocks)
    # A table's cells are kept whatever their size or length, and its bold ones are not section titles.
    sized = [b for b in blocks if b.table is not None or b.size >= body_size * MIN_SIZE_RATIO]
    headings = {id(b) for b in sized if b.table is None and is_heading(b, body_size)}
    kept = [b for b in sized if b.table is not None or id(b) in headings or len(b.text.split()) >= MIN_WORDS]
    content = [piece for block in kept for piece in _pieces(block)]
    use_overlap = not headings

    drafts: list[ChunkDraft] = []
    section: str | None = None
    current: list[Block] = []

    for block in content:
        if id(block) in headings:
            if current:
                drafts.append(_draft(len(drafts), current, section))
            current, section = [], block.text
            continue

        size = sum(len(b.text) for b in current)
        # A table stays in one chunk up to BLOCK_CAP: split at max_chars, 52% of its numbers lost their column header.
        same_table = bool(current) and block.table is not None and block.table == current[-1].table
        changes_table = bool(current) and block.table != current[-1].table
        too_long = size + len(block.text) > (BLOCK_CAP if same_table else max_chars)
        if current and (block.page != current[-1].page or too_long or changes_table):
            drafts.append(_draft(len(drafts), current, section))
            last = current[-1]
            carry = use_overlap and not changes_table and last.page == block.page
            carry = carry and len(last.text) <= OVERLAP_MAX_CHARS
            current = [last] if carry else []
        current = [*current, block]

    if current:
        drafts.append(_draft(len(drafts), current, section))
    return drafts
