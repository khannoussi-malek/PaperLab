"""The sentences of a chat answer and the passages each cites (M34): what answer check sends to the model, one by one.

A sentence's citations are the [C#] markers inside it or right after its final punctuation ("... BLEU [C2]." or
"... BLEU. [C2]"). [N#] note markers are removed but not counted: a note is the reader's text, never checked (D118).
Headings, table separator rows and :::note suggestion blocks are skipped; a list item or table row is its own unit.
"""

import re
from dataclasses import dataclass

from app.core.notes import _CITATION

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_ROW = re.compile(r"^\s*\|")
_MARKERS = r"(?:\s*\[[CN]\d+\])*"
# A sentence ends at . ! or ? (plus any markers right after it) followed by space and a capital or a digit.
_END = re.compile(rf"[.!?]{_MARKERS}(?=\s+[A-Z0-9])")
# Words whose dot is not a sentence end.
_NOT_AN_END = re.compile(r"(?:\b(?:e\.g|i\.e|vs|et al|cf|approx|Fig|No)|\d)\.$", re.IGNORECASE)


@dataclass(frozen=True)
class AnswerSentence:
    index: int
    text: str  # markers removed, whitespace collapsed
    labels: tuple[str, ...]  # the C labels it cites, in first-appearance order


def _units(content: str) -> list[str]:
    """Paragraphs, with list items and table rows as units of their own; headings and note blocks dropped."""
    units, paragraph, in_note = [], [], False

    def flush():
        if paragraph:
            units.append(" ".join(paragraph))
            paragraph.clear()

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(":::"):
            flush()
            in_note = stripped.startswith(":::note") or (in_note and stripped != ":::")
            continue
        if in_note:
            continue
        if not stripped or _HEADING.match(line) or _TABLE_SEPARATOR.match(line):
            flush()
            continue
        if _LIST_ITEM.match(line) or _TABLE_ROW.match(line):
            flush()
            units.append(_LIST_ITEM.sub("", line, count=1).strip().strip("|").replace("|", " "))
            continue
        paragraph.append(stripped)
    flush()
    return units


def _split(unit: str) -> list[str]:
    pieces, start = [], 0
    for match in _END.finditer(unit):
        head = unit[start : match.start() + 1]
        if _NOT_AN_END.search(head):
            continue
        pieces.append(unit[start : match.end()])
        start = match.end()
    pieces.append(unit[start:])
    return [p.strip() for p in pieces if p.strip()]


def _sentence(index: int, raw: str) -> AnswerSentence | None:
    labels = tuple(dict.fromkeys(f"{kind}{n}" for kind, n in _CITATION.findall(raw) if kind == "C"))
    text = " ".join(_CITATION.sub("", raw).split())
    text = re.sub(r"\s+([.!?,;:])", r"\1", text)
    if not re.search(r"\w", text):
        return None
    return AnswerSentence(index, text, labels)


def answer_sentences(content: str) -> list[AnswerSentence]:
    out: list[AnswerSentence] = []
    for unit in _units(content):
        for raw in _split(unit):
            sentence = _sentence(len(out), raw)
            if sentence is not None:
                out.append(sentence)
    return out
