"""How a finding line is cleaned and guarded, shared by section review and the exit-test check (D118).
Each caller keeps its own rules (word cap, citation form, what a bad citation does); only the shape is shared."""

import re
from collections.abc import Iterable
from typing import Literal

Kind = Literal["missing", "unsupported", "supported"]

_LINE = re.compile(r"^(Missing|Unsupported|Supported)\s*:\s*(.+)$", re.IGNORECASE)
LABEL_START = re.compile(r"^(Missing|Unsupported|Supported)\b", re.IGNORECASE)
_PREFIX = re.compile(r"^[\s>\-\u2022]*(\d+[.)]\s*)?")
_MARKUP = re.compile(r"[*_]+")  # backticks stay: they quote wording
# A point is judged by its shape (D118): no quote mark, no colon/semicolon/dash/bracket introducing 3+ words, no
# suggestion phrase, no run copied from the section. Deliberately conservative: honest points that trip a rule
# are dropped and counted.
# Every quote-like code point except the apostrophe forms (' and \u2019), which count only when they open a word.
_QUOTE = re.compile(
    '["`\u00ab\u00bb\u02ba\u02ee\u2018\u201a-\u201f\u2032-\u2037\u2039\u203a\u275b-\u2760'
    "\u300c-\u300f\u301d-\u301f\uff02\uff07]|(?<!\\w)['\u2019](?=\\w)"
)
INTRODUCES = re.compile(r"(:\s+|;\s*|\s?[\u2014\u2013]\s?|\s-\s|[(\[{]\s*)[^\s)\]}]+(\s+[^\s)\]}]+){2,}")
SUGGEST = re.compile(
    r"\b(phrase|phrasing|reword|rephrase|rewrite|re-write|suggest(ed|ion)?|replace|instead of|such as|"
    r"for example|for instance|how about|word(ed|ing)?\s+(it\s+)?as|(say|saying|said)\s+as|"
    r"(line|sentence|phrase)\s+like|change\s+(it|this)\s+to|consider\s+(writing|adding|saying)|"
    r"should\s+(read|say)|you\s+(could|can|might|may)\s+(say|write|use)|try(ing)?\s+(saying|writing|adding|using)|"
    r"try:|says|saying|said|fram(e|ed|ing)\s+(it\s+)?as|along\s+the\s+lines\s+of|"
    r"(open|opens|opening|begin|begins|beginning|start|starts|starting|lead|leads|leading)\s+with|"
    r"the\s+sentence|a\s+statement|would\s+(be\s+clearer|read\s+better))\b|\be\.g\.",
    re.I,
)
COPY_WORDS = 6  # a point sharing this many consecutive words with a sentence of the section is copying it


def clean_line(raw: str) -> str:
    """The line without list numbering, bullets and markdown emphasis."""
    return " ".join(_MARKUP.sub("", _PREFIX.sub("", raw, count=1)).split())


def split_label(cleaned: str) -> tuple[Kind, str] | None:
    match = _LINE.match(cleaned)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).strip()  # type: ignore[return-value]


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def grams(texts: Iterable[str]) -> set[tuple[str, ...]]:
    out: set[tuple[str, ...]] = set()
    for text in texts:
        words = _words(text)
        out.update(tuple(words[i : i + COPY_WORDS]) for i in range(len(words) - COPY_WORDS + 1))
    return out


def bare(point: str, ref: re.Pattern[str]) -> str:
    return ref.sub(" ", point)


def reads_as_wording(point: str, ref: re.Pattern[str], copied: set[tuple[str, ...]]) -> bool:
    plain = bare(point, ref)
    return bool(_QUOTE.search(point) or INTRODUCES.search(plain) or SUGGEST.search(point) or grams([plain]) & copied)
