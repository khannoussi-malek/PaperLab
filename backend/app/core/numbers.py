"""Reading numbers the way papers print them. The one parser: cells and captured numbers both go through here.

Handles "88.5", "−3", "1,234", "88.5 ± 0.3", "34%", "110M", "1.2e-3", and best-result or footnote marks ("90.9*",
"90.9†", "**90.9**"). A cell that isn't exactly one of those ("BERT-L", "—", "88.5 F1") has no value: it's a label.
ponytail: "." is the only decimal separator ("1,5" is not 1.5), and "1.2×10^-3" isn't read; add them when a paper
needs them.
"""

import re
from dataclasses import dataclass

_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+"
# Whitespace only before a suffix or "%", so a match never swallows the space before the next word.
_AMOUNT = rf"[+-]?(?:{_NUMBER})(?:\s*[KMB])?(?:\s*%)?"
_WITH_ERROR = re.compile(rf"(?P<value>{_AMOUNT})(?:\s*±\s*(?P<error>{_AMOUNT}))?")
_PARTS = re.compile(rf"(?P<sign>[+-]?)(?P<number>{_NUMBER})\s*(?P<suffix>[KMB]?)")
_SCALE = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}
_MARKS = "*†‡§¶"
_NOT_UNITS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "vs", "with"}
_UNIT = re.compile(r"\s*([A-Za-z][\w@-]{0,15})")


@dataclass(frozen=True)
class ParsedNumber:
    value: float | None
    error: float | None


@dataclass(frozen=True)
class NumberCandidate:
    raw: str
    value: float
    error: float | None
    unit_hint: str | None


def _clean(raw: str) -> str:
    text = raw.replace("−", "-").strip()
    if text.startswith("**") and text.endswith("**"):
        text = text[2:-2].strip()
    return text.rstrip(_MARKS).strip()


def _amount(text: str) -> float:
    parts = _PARTS.match(text)
    assert parts is not None  # only called on text _AMOUNT matched
    number = float(parts["number"].replace(",", "")) * _SCALE[parts["suffix"]]
    return -number if parts["sign"] == "-" else number


def parse_number(raw: str) -> ParsedNumber:
    match = _WITH_ERROR.fullmatch(_clean(raw))
    if match is None:
        return ParsedNumber(value=None, error=None)
    error = match["error"]
    return ParsedNumber(value=_amount(match["value"]), error=None if error is None else _amount(error))


def find_numbers(text: str) -> list[NumberCandidate]:
    """Every number in a selection, in order, for the owner to pick from. Digits inside words ("GPT-2", "v2",
    "3x") are skipped. unit_hint is "%" or the word right after the number, unless that word is a common short word."""
    text = text.replace("−", "-")
    found = []
    for match in _WITH_ERROR.finditer(text):
        before = text[match.start() - 1] if match.start() > 0 else " "
        after = text[match.end()] if match.end() < len(text) else " "
        starts_unsigned = match.group(0)[0] not in "+-"
        if before.isalnum() or before in "._" or (starts_unsigned and before in "+-") or after.isalnum():
            continue
        raw = match.group(0).strip()
        if raw.endswith("%"):
            unit = "%"
        else:
            word = _UNIT.match(text, match.end())
            unit = word[1] if word and word[1].lower() not in _NOT_UNITS else None
        parsed = parse_number(raw)
        found.append(NumberCandidate(raw=raw, value=parsed.value, error=parsed.error, unit_hint=unit))
    return found
