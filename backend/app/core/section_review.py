"""Section review (M27 slice E): judge one manuscript section against its role's checklist. It answers only in
Missing/Unsupported/Supported points that refer to the researcher's own sentences or notes, never replacement text
(D118): the parser drops any line that looks like a rewrite. Writes no llm_outputs row; provenance is `model`.

Accepted limit: a shape rule cannot catch every paraphrase. The review is display-only (never inserted into the
source) and each point is capped at MAX_WORDS words, so what slips through is a short gist, not pasteable prose."""

import re
from dataclasses import dataclass
from typing import Literal

from app.core import prompts
from app.core.finding_lines import (
    INTRODUCES,
    LABEL_START,
    SUGGEST,
    Kind,
    bare,
    clean_line,
    grams,
    reads_as_wording,
    split_label,
)
from app.core.section_rubrics import rubric_for

PROMPT_VERSION = 2
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("section_review", PROMPT_VERSION).split("\n<!-- prompt -->\n")
MAX_WORDS = 20  # not counting [S#]/[N#] citations
MAX_LINES = 12
MODEL_ERROR = "model_error"
RETRY = (
    "\n\nReply again with lines only. Each line starts with Missing:, Unsupported: or Supported:, has at most "
    "20 words, and cites [S#] or [N#] where it points at something."
)

_REF = re.compile(r"\[([SN])(\d+)\]")


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


def _finding(line: str, n_sentences: int, n_notes: int, copied: set[tuple[str, ...]]) -> Finding | None:
    labelled = split_label(line)
    if not labelled:
        return None
    kind, point = labelled
    if len(bare(point, _REF).split()) > MAX_WORDS or reads_as_wording(point, _REF, copied):
        return None
    refs = tuple(Ref(k, int(n)) for k, n in _REF.findall(point))
    if any(r.n < 1 or r.n > (n_sentences if r.kind == "S" else n_notes) for r in refs):
        return None
    if kind != "missing" and not refs:
        return None
    return Finding(kind, point, refs)


def parse_findings(reply: str, sentences: list[str], n_notes: int) -> tuple[list[Finding], int]:
    """Kept lines (at most MAX_LINES) and the count of dropped ones, including lines past the cap.

    A line is a candidate when it starts with a label word or reads like a rewrite offer (a suggestion phrase or a
    colon/dash/semicolon/bracket introducing wording); plain chatter is ignored.
    An exact repeat of an earlier line is skipped silently.
    """
    copied = grams(sentences)
    kept: list[Finding] = []
    seen: set[str] = set()
    dropped = 0
    for raw in reply.splitlines():
        line = clean_line(raw)
        candidate = LABEL_START.match(line) or SUGGEST.search(line) or INTRODUCES.search(bare(line, _REF))
        if not candidate or line.lower() in seen:
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
