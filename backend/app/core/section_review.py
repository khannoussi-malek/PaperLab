"""Section review (M27 slice E): judge one manuscript section against its role's checklist. It answers only in
Missing/Unsupported/Supported points that refer to the researcher's own sentences or notes, never replacement text
(D118): the parser drops any line that looks like a rewrite. Writes no llm_outputs row; provenance is `model`."""

import re
from dataclasses import dataclass
from typing import Literal

from app.core import prompts
from app.core.section_rubrics import rubric_for

PROMPT_VERSION = 2
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("section_review", PROMPT_VERSION).split("\n<!-- prompt -->\n")
MAX_WORDS = 25
MAX_LINES = 12
MODEL_ERROR = "model_error"
RETRY = (
    "\n\nReply again with lines only. Each line starts with Missing:, Unsupported: or Supported:, has at most "
    "25 words, and cites [S#] or [N#] where it points at something."
)

_LINE = re.compile(r"^(Missing|Unsupported|Supported)\s*:\s*(.+)$", re.IGNORECASE)
_PREFIX = re.compile(r"^[\s>\-\u2022]*(\d+[.)]\s*)?")
_MARKUP = re.compile(r"[*_`]+")
_REF = re.compile(r"\[([SN])(\d+)\]")
# A point is judged by its shape (D118): no quoted span, no colon/dash introducing wording, no suggestion phrase,
# no run copied from the section. Deliberately conservative: honest points that trip a rule are dropped and counted.
_QUOTE = re.compile(
    r"\"[^\"]*\"|\u201c[^\u201c\u201d]*[\u201c\u201d]|\u2018[^\u2018\u2019]*\u2019|\u00ab[^\u00ab\u00bb]*\u00bb"
    r"|\u201e[^\u201e\u201c\u201d]*[\u201c\u201d]|(?<!\w)'[^'\s][^']*\s[^']*'(?!\w)"
)
_OPEN_QUOTE = re.compile(r"[\"\u201c\u2018\u00ab\u201e]")
_INTRODUCES = re.compile(r"(:\s+|\s?[\u2014\u2013]\s?|\s-\s)\S+(\s+\S+){2,}")
_SUGGEST = re.compile(
    r"\b(phrase|phrasing|reword|rephrase|rewrite|re-write|suggest(ed|ion)?|replace|instead of|such as|"
    r"for example|for instance|how about|word(ed|ing)?\s+(it\s+)?as|(say|saying|said)\s+as|"
    r"(line|sentence|phrase)\s+like|change\s+(it|this)\s+to|consider\s+(writing|adding|saying)|"
    r"should\s+(read|say)|you\s+(could|can|might|may)\s+(say|write|use)|try(ing)?\s+(saying|writing|adding|using)|"
    r"try:)\b|\be\.g\.",
    re.I,
)
COPY_WORDS = 6  # a point sharing this many consecutive words with a sentence of the section is copying it

Kind = Literal["missing", "unsupported", "supported"]


@dataclass(frozen=True)
class Ref:
    kind: Literal["S", "N"]  # a numbered sentence or one of the researcher's notes
    n: int


@dataclass(frozen=True)
class Finding:
    kind: Kind
    point: str
    refs: tuple[Ref, ...]


@dataclass(frozen=True)
class Review:
    findings: list[Finding]
    dropped: int
    model: str


class ReviewFailed(Exception):
    pass


def build_prompt(role: str, sentences: list[str], notes: list[str]) -> str:
    checklist = "\n".join(f"- {item.text}" for item in rubric_for(role))
    numbered = "\n".join(f"[S{i}] {s}" for i, s in enumerate(sentences, 1))
    noted = "\n".join(f"[N{i}] {n}" for i, n in enumerate(notes, 1)) or "No notes."
    return PROMPT_TEMPLATE.format(role=role, checklist=checklist, sentences=numbered, notes=noted)


def _clean(line: str) -> str:
    """The line without list numbering, bullets and markdown emphasis."""
    return " ".join(_MARKUP.sub("", _PREFIX.sub("", line, count=1)).split())


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _grams(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + COPY_WORDS]) for i in range(len(words) - COPY_WORDS + 1)}


def _wording(point: str, copied: set[tuple[str, ...]]) -> bool:
    bare = _REF.sub(" ", point)
    return bool(
        _QUOTE.search(point)
        or _OPEN_QUOTE.search(point)
        or _INTRODUCES.search(bare)
        or _SUGGEST.search(point)
        or _grams(_words(bare)) & copied
    )


def _finding(line: str, n_sentences: int, n_notes: int, copied: set[tuple[str, ...]]) -> Finding | None:
    match = _LINE.match(line)
    if not match:
        return None
    kind, point = match.group(1).lower(), match.group(2).strip()
    if len(point.split()) > MAX_WORDS or _wording(point, copied):
        return None
    refs = tuple(Ref(k, int(n)) for k, n in _REF.findall(point))
    if any(r.n < 1 or r.n > (n_sentences if r.kind == "S" else n_notes) for r in refs):
        return None
    if kind != "missing" and not refs:
        return None
    return Finding(kind, point, refs)  # type: ignore[arg-type]


def parse_findings(reply: str, sentences: list[str], n_notes: int) -> tuple[list[Finding], int]:
    """Kept lines (at most MAX_LINES) and the count of dropped ones, including lines past the cap.

    A line is a candidate when it starts with a label or reads like a rewrite offer; plain chatter is ignored.
    An exact repeat of an earlier line is skipped silently.
    """
    copied = set().union(*(_grams(_words(t)) for t in sentences)) if sentences else set()
    kept: list[Finding] = []
    seen: set[str] = set()
    dropped = 0
    for raw in reply.splitlines():
        line = _clean(raw)
        if not (_LINE.match(line) or _SUGGEST.search(line)) or line.lower() in seen:
            continue
        seen.add(line.lower())
        finding = _finding(line, len(sentences), n_notes, copied)
        if finding is not None and len(kept) < MAX_LINES:
            kept.append(finding)
        else:
            dropped += 1
    return kept, dropped


async def review(role: str, sentences: list[str], notes: list[str], *, llm) -> Review:
    model = getattr(llm, "model", "unknown")
    prompt = build_prompt(role, sentences, notes)
    for attempt in (prompt, prompt + RETRY):
        reply = "".join([t async for t in llm.stream(SYSTEM_PROMPT, attempt)])
        findings, dropped = parse_findings(reply, sentences, len(notes))
        if findings:
            return Review(findings, dropped, model)
    raise ReviewFailed(MODEL_ERROR)
