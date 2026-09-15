"""The words inside a box the owner drew over a table, laid out as a proposed grid for the owner to fix.

No detection: the owner already said "this is a table". Rows are words sharing a line. Columns are split at vertical
gaps that almost every row leaves empty; "almost" lets a title row or a centred group label ("Published") cross a
gap without merging the columns under it. Measured on real papers: 3 of 5 tables came out right with no fixing,
the other 2 needed one column merge.
ponytail: a heuristic, not a model; the grid editor is the fix for what it gets wrong. A table model can later fill
the same grid.
"""

import re
import statistics
from dataclasses import dataclass

Rect = tuple[float, float, float, float]

# A word joins the current row when their vertical spans overlap by half the smaller height (subscripts stay in).
ROW_OVERLAP = 0.5
# Words closer than this many line heights are one phrase ("WSJ only, discriminative"); column gaps are wider.
PHRASE_GAP = 0.6
# A gap narrower than this many line heights is a space, not a column boundary.
MIN_COLUMN_GAP = 0.5
# Up to this many rows may cross a column gap: a title row and a group label.
SPANNING_ROWS = 2
# A caption this close (points) above or below the box names the dataset.
CAPTION_GAP = 36.0
CAPTION_NAME_CHARS = 120
_CAPTION = re.compile(r"Table\s+\d+\s*[:.]")


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class GridCell:
    text: str
    bbox: Rect | None  # the union of its words; None for an empty cell


def _union(a: Rect, b: Rect) -> Rect:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _rows(words: list[Word]) -> list[list[Word]]:
    rows: list[tuple[float, float, list[Word]]] = []
    for word in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        if rows:
            top, bottom, members = rows[-1]
            overlap = min(bottom, word.y1) - max(top, word.y0)
            if overlap >= ROW_OVERLAP * min(word.y1 - word.y0, bottom - top):
                rows[-1] = (min(top, word.y0), max(bottom, word.y1), [*members, word])
                continue
        rows.append((word.y0, word.y1, [word]))
    return [sorted(members, key=lambda w: w.x0) for _, _, members in rows]


def _phrases(row: list[Word], gap: float) -> list[GridCell]:
    phrases: list[GridCell] = []
    for word in row:
        box: Rect = (word.x0, word.y0, word.x1, word.y1)
        last = phrases[-1] if phrases else None
        if last and last.bbox and word.x0 - last.bbox[2] <= gap:
            phrases[-1] = GridCell(f"{last.text} {word.text}", _union(last.bbox, box))
        else:
            phrases.append(GridCell(word.text, box))
    return phrases


def _separators(rows: list[list[GridCell]], min_gap: float) -> list[float]:
    """Midpoints of the x ranges that few rows reach, inside the table's own left and right edge."""
    # Fewer than all rows: in a two-row table, every x is reached by at most two rows.
    allowed = min(SPANNING_ROWS, len(rows) - 1)
    # A row counts once where its own phrases overlap, so merge each row's intervals first.
    counts: dict[float, int] = {}
    for row in rows:
        spans = sorted((c.bbox[0], c.bbox[2]) for c in row if c.bbox)
        merged: list[list[float]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            counts[start] = counts.get(start, 0) + 1
            counts[end] = counts.get(end, 0) - 1
    xs = sorted(counts)
    separators, covered, gap_start = [], 0, None
    for x in xs[:-1]:  # past the last x nothing is covered, and that edge is not a column boundary
        covered += counts[x]
        if covered <= allowed:
            gap_start = x if gap_start is None else gap_start
            continue
        if gap_start is not None and x - gap_start >= min_gap:
            separators.append((gap_start + x) / 2)
        gap_start = None
    return separators


def words_to_grid(words: list[Word]) -> list[list[GridCell]]:
    """Rows of cells, top to bottom and left to right. Every column has text: a separator only sits where at most
    SPANNING_ROWS rows reach, so more rows than that start a phrase between any two separators."""
    if not words:
        return []
    height = statistics.median(w.y1 - w.y0 for w in words)
    rows = [_phrases(row, PHRASE_GAP * height) for row in _rows(words)]
    separators = _separators(rows, MIN_COLUMN_GAP * height)
    grid: list[list[GridCell]] = []
    for row in rows:
        cells = [GridCell("", None) for _ in range(len(separators) + 1)]
        for phrase in row:
            assert phrase.bbox is not None
            column = sum(1 for s in separators if s < phrase.bbox[0])
            current = cells[column]
            text = f"{current.text} {phrase.text}".strip()
            cells[column] = GridCell(text, phrase.bbox if current.bbox is None else _union(current.bbox, phrase.bbox))
        grid.append(cells)
    return grid


def caption_name(blocks: list[tuple[Rect, str]], region: Rect) -> str | None:
    """The nearest "Table N: …" caption above, below or inside the box, cut after its first sentence."""
    best: tuple[float, str] | None = None
    for (x0, y0, x1, y1), text in blocks:
        line = " ".join(text.split())
        overlaps = min(x1, region[2]) > max(x0, region[0])
        distance = max(region[1] - y1, y0 - region[3])
        if not (_CAPTION.match(line) and overlaps and distance <= CAPTION_GAP):
            continue
        if best is None or distance < best[0]:
            best = (distance, line)
    if best is None:
        return None
    line = best[1]
    head = _CAPTION.match(line)
    assert head is not None
    end = line.find(". ", head.end())
    name = line if end == -1 else line[: end + 1]
    if len(name) <= CAPTION_NAME_CHARS:
        return name
    return name[: CAPTION_NAME_CHARS - 1].rsplit(" ", 1)[0] + "…"
