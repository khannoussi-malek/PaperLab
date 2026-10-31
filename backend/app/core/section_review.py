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
MAX_QUOTE_WORDS = 6
MODEL_ERROR = "model_error"
RETRY = (
    "\n\nReply again with lines only. Each line starts with Missing:, Unsupported: or Supported:, has at most "
    "25 words, and cites [S#] or [N#] where it points at something."
)

_LINE = re.compile(r"^(Missing|Unsupported|Supported)\s*:\s*(.+)$", re.IGNORECASE)
_PREFIX = re.compile(r"^[\s>\-\u2022]*(\d+[.)]\s*)?")
_MARKUP = re.compile(r"[*_`]+")
_REF = re.compile(r"\[([SN])(\d+)\]")
# Closed quoted runs in every style: "a", “a”, ‘a’, «a», „a“.
_QUOTE = re.compile(
    r"\"([^\"]*)\"|\u201c([^\u201c\u201d]*)[\u201c\u201d]|\u2018([^\u2018\u2019]*)\u2019|\u00ab([^\u00ab\u00bb]*)\u00bb"
    r"|\u201e([^\u201e\u201c\u201d]*)[\u201c\u201d]"
)
_OPEN_QUOTE = re.compile(r"[\"\u201c\u2018\u00ab\u201e]([^\"\u201c\u201d\u2018\u2019\u00ab\u00bb\u201e]*)$")
# Deliberately conservative (D118): "instead of" / "rewrite" also drop honest points; tune from the eval's dropped.
_REWRITE = re.compile(
    r"(re-?write|replace (it|this)|should (read|say)|change (it|this) to|instead of|try:"
    r"|you (could|can|might|may) (say|write|use)|\b(add|use|write|say|insert):"
    r"|\b(add|write|say|use|insert)\b[^.]*\bsuch as"
    r"|(e\.g\.|for example|for instance),?\s*(write|say|use)\b"
    r"|(e\.g\.|for example|for instance),?[^\"\u201c\u2018\u00ab\u201e:]*[:\"\u201c\u2018\u00ab\u201e])",
    re.I,
)

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


def _quoted_wording(point: str) -> bool:
    runs = [next(g for g in m.groups() if g is not None) for m in _QUOTE.finditer(point)]
    unclosed = _OPEN_QUOTE.search(_QUOTE.sub(" ", point))
    return any(len(r.split()) >= MAX_QUOTE_WORDS for r in runs) or bool(
        unclosed and len(unclosed.group(1).split()) >= MAX_QUOTE_WORDS
    )


def _finding(line: str, n_sentences: int, n_notes: int) -> Finding | None:
    match = _LINE.match(line)
    if not match:
        return None
    kind, point = match.group(1).lower(), match.group(2).strip()
    if len(point.split()) > MAX_WORDS or _REWRITE.search(point) or _quoted_wording(point):
        return None
    refs = tuple(Ref(k, int(n)) for k, n in _REF.findall(point))
    if any(r.n < 1 or r.n > (n_sentences if r.kind == "S" else n_notes) for r in refs):
        return None
    if kind != "missing" and not refs:
        return None
    return Finding(kind, point, refs)  # type: ignore[arg-type]


def parse_findings(reply: str, n_sentences: int, n_notes: int) -> tuple[list[Finding], int]:
    """Kept lines (at most MAX_LINES) and the count of dropped ones, including lines past the cap.

    A line is a candidate when it starts with a label or reads like a rewrite offer; plain chatter is ignored.
    An exact repeat of an earlier line is skipped silently.
    """
    kept: list[Finding] = []
    seen: set[str] = set()
    dropped = 0
    for raw in reply.splitlines():
        line = _clean(raw)
        if not (_LINE.match(line) or _REWRITE.search(line)) or line.lower() in seen:
            continue
        seen.add(line.lower())
        finding = _finding(line, n_sentences, n_notes)
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
        findings, dropped = parse_findings(reply, len(sentences), len(notes))
        if findings:
            return Review(findings, dropped, model)
    raise ReviewFailed(MODEL_ERROR)
