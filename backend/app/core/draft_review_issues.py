"""Whole-draft review, the pure half (S2P B7): the paper text the model reads, issue checks, quote location, merge.
No model, no database. An issue is filed only with an exact quote of the paper and a close criterion (D118)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.finding_lines import reads_as_wording
from app.core.manuscript_sections import _INPUT, _target
from app.core.manuscript_sentences import _blank_comments

SEVERITIES = ("blocker", "major", "minor", "nit")
MIN_PAPER_CHARS = 200
MAX_PAPER_CHARS = 40_000  # about 10k tokens: with the prompt and the answer it fits OLLAMA_NUM_CTX = 16 384
MAX_TOTAL_CHARS = 160_000  # a longer draft is refused; a draft up to this is reviewed in parts of MAX_PAPER_CHARS
MAX_DEPTH = 4
MIN_QUOTE, MAX_QUOTE = 12, 400
MAX_WORDS = 40
NO_REF = re.compile(r"(?!)")  # a point here cites nothing
HEADING = re.compile(r"^\\(?:section|chapter)\*?", re.MULTILINE)
BLANK = re.compile(r"\n\s*\n")


class RawIssue(BaseModel):  # extra keys are ignored: local models add them
    severity: Literal["blocker", "major", "minor", "nit"]
    section: str = Field(max_length=120)
    summary: str = Field(min_length=1)
    evidence_quote: str
    close_criterion: str = Field(min_length=1)


@dataclass(frozen=True)
class Place:
    file: str
    line: int
    start: int
    end: int


@dataclass(frozen=True)
class Issue:
    severity: str
    section: str
    summary: str
    quote: str
    close_criterion: str
    raised_by: tuple[str, ...]
    place: Place


def assemble(files: Mapping[str, str], main: str) -> tuple[str, dict[str, str]]:
    """(the paper's text, the raw text of every file that went in): `main` with each `\\input`/`\\include` of a present
    file replaced by that file, comments blanked, cut to what lies between \\begin{document} and \\end{document}."""
    used: dict[str, str] = {}

    def expand(path: str, stack: tuple[str, ...]) -> str:
        used[path] = files[path]
        text = _blank_comments(files[path])
        if len(stack) >= MAX_DEPTH:
            return text

        def sub(m: re.Match) -> str:
            target = _target(m)
            return m.group(0) if target not in files or target in stack else f"\n{expand(target, (*stack, target))}\n"

        return _INPUT.sub(sub, text)

    text = expand(main, (main,))
    begin = text.find("\\begin{document}")
    if begin >= 0:
        text = text[begin + len("\\begin{document}") :]
    end = text.find("\\end{document}")
    return (text if end < 0 else text[:end]).strip(), used


def _blocks(paper: str) -> list[str]:
    """The paper cut before each heading line; the text before the first heading is a block of its own."""
    starts = sorted({0, *(m.start() for m in HEADING.finditer(paper))})
    return [paper[a:b] for a, b in zip(starts, [*starts[1:], len(paper)])]


def _units(block: str, limit: int) -> list[str]:
    """A block that fits is one unit; a longer one is cut after its blank lines, and a paragraph still over the limit
    is cut every `limit` characters. The units concatenate back to the block."""
    if len(block) <= limit:
        return [block]
    pieces, start = [], 0
    for m in BLANK.finditer(block):
        pieces.append(block[start : m.end()])
        start = m.end()
    pieces.append(block[start:])
    return [part for piece in pieces for part in (piece[i : i + limit] for i in range(0, len(piece), limit)) if part]


def split_parts(paper: str, limit: int = MAX_PAPER_CHARS) -> list[str]:
    """The paper in parts of at most `limit` characters, cut at section headings where it can be, greedily packed.
    `"".join(parts) == paper` always, so a quote is found in the part that holds it."""
    if len(paper) <= limit:
        return [paper]
    units = [unit for block in _blocks(paper) for unit in _units(block, limit)]
    parts: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) > limit:
            parts.append(current)
            current = ""
        current += unit
    return [*parts, current]


def locate(files: Mapping[str, str], quote: str) -> Place | None:
    """Where `quote` stands in the files (whitespace-flexible, comments never match), or None."""
    words = quote.split()
    if not words or not MIN_QUOTE <= len(" ".join(words)) <= MAX_QUOTE:
        return None
    pattern = re.compile(r"\s+".join(map(re.escape, words)))
    for path, raw in files.items():
        text = _blank_comments(raw)
        found = pattern.search(text)
        if found:
            return Place(path, text.count("\n", 0, found.start()) + 1, found.start(), found.end())
    return None


def check_issue(raw: object, lens: str, files: Mapping[str, str], copied: set[tuple[str, ...]],
                paper: str) -> tuple[Issue | None, str | None]:
    """(issue, None) or (None, why): why is invalid, criterion, quote or wording. The quote must stand in a used file
    AND in the paper text the model read (a quote from the preamble or the tail was never shown to it)."""
    if not isinstance(raw, dict):
        return None, "invalid"
    if not str(raw.get("close_criterion") or "").strip():  # missing, empty or blank: no criterion, no issue
        return None, "criterion"
    try:
        item = RawIssue.model_validate(raw)
    except ValidationError:
        return None, "invalid"
    place = locate(files, item.evidence_quote)
    if place is None or " ".join(item.evidence_quote.split()) not in " ".join(paper.split()):
        return None, "quote"
    for point in (item.summary, item.close_criterion, item.section):
        if len(point.split()) > MAX_WORDS or reads_as_wording(point, NO_REF, copied):
            return None, "wording"
    return Issue(item.severity, item.section, item.summary, " ".join(item.evidence_quote.split()),
                 item.close_criterion, (lens,), place), None


def order(files: Mapping[str, str]):
    """Sort key: severity, then document order (files in paper order), then offset."""
    rank = {path: n for n, path in enumerate(files)}
    return lambda i: (SEVERITIES.index(i.severity), rank.get(i.place.file, len(rank)), i.place.start)


def overlaps(a: Place, b: Place) -> bool:
    return a.file == b.file and a.start < b.end and b.start < a.end


def unseen(issues: list[Issue], seen: list[Place]) -> list[Issue]:
    """The issues whose span overlaps none of the `seen` spans (an earlier round's candidates, refuted ones too)."""
    return [i for i in issues if not any(overlaps(i.place, p) for p in seen)]


def merge(issues: list[Issue], files: Mapping[str, str]) -> list[Issue]:
    """One issue per overlapping span: the higher severity wins, `raised_by` lists every lens; sorted by severity."""
    out: list[Issue] = []
    for issue in sorted(issues, key=order(files)):
        at = next((i for i, kept in enumerate(out) if overlaps(kept.place, issue.place)), None)
        if at is None:
            out.append(issue)
        else:
            out[at] = replace(out[at], raised_by=tuple(sorted({*out[at].raised_by, *issue.raised_by})))
    return out
