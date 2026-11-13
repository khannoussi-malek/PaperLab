"""Whole-draft review, the model half (S2P B7). Three fixed lenses read the whole paper, their issues are checked,
merged and sorted, and skeptics try to refute each issue. Light: 1 skeptic, 1 round, at most 11 calls. Full: 3 angled
skeptics, up to 2 rounds, stop early when a round is dry, at most 54 calls. A draft over MAX_PAPER_CHARS is split into
parts and each lens reads each part (the calls grow with the parts). An issue is dropped when a majority of its
skeptics refute it. It judges and never writes wording (D118). The pure half is draft_review_issues."""

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.core import prompts
from app.core.draft_review_issues import (
    MAX_WORDS,
    NO_REF,
    Issue,
    Place,
    check_issue,
    merge,
    order,
    split_parts,
    unseen,
)
from app.core.finding_lines import grams, reads_as_wording
from app.core.llm_json import ask_json
from app.providers.base import LLMError

PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("draft_review", PROMPT_VERSION).split("\n<!-- prompt -->\n")
VERIFY_SYSTEM_PROMPT, VERIFY_TEMPLATE = prompts.load("draft_verify", PROMPT_VERSION).split("\n<!-- prompt -->\n")
MAX_PER_REVIEWER = 8
MAX_ISSUES = 8  # per round, that reach the skeptics
PROMPT_TOKENS = 700  # instructions and the answer, per call: used by the estimate only
MASKED_REASON = "The skeptic found this unconvincing."
PART_NOTE = (
    "[Part {p} of {total} of the paper. The other parts are reviewed separately, "
    "so something missing here may be in another part.]\n\n"
)
Mode = Literal["light", "full"]


@dataclass(frozen=True)
class Lens:
    id: str
    name: str
    focus: str


LENSES = (
    Lens(
        "ideas",
        "Ideas and definitions",
        "definitions against how they are used, notation that changes meaning, "
        "whether the method supports the contribution, gaps in a derivation or argument, "
        "claims broader than the evidence",
    ),
    Lens(
        "evidence",
        "Evidence and experiments",
        "evaluation design, baselines, metrics, ablations, whether the "
        "experiments back each claim, abstract and conclusion numbers against the results",
    ),
    Lens(
        "practice",
        "Practical use",
        "practicality, cost and speed claims, reproducibility, whether a reader could "
        "repeat the work, deployment realism",
    ),
)
ANGLES_LIGHT = (
    "Is the issue wrong because it misreads the paper (says something is missing or wrong that is present), "
    "or because the paper already handles the concern elsewhere?",
)
ANGLES_FULL = (
    "Misreading: the issue says something is wrong or missing that is actually present in the paper.",
    "Already addressed: the concern is handled elsewhere in the paper.",
    "Scope or severity: the issue is real but out of scope for a draft at this stage, or its severity is overstated.",
)


@dataclass(frozen=True)
class ModeSpec:
    angles: tuple[str, ...]
    rounds: int
    expected: tuple[int, ...]  # issues expected per round, for the estimate only


MODES: dict[str, ModeSpec] = {"light": ModeSpec(ANGLES_LIGHT, 1, (8,)), "full": ModeSpec(ANGLES_FULL, 2, (8, 4))}


def max_calls(mode: Mode, parts: int = 1) -> int:
    spec = MODES[mode]
    return spec.rounds * (len(LENSES) * parts + MAX_ISSUES * len(spec.angles))  # one part: light 11, full 54


def likely_calls(mode: Mode, parts: int = 1) -> int:
    spec = MODES[mode]
    return sum(len(LENSES) * parts + n * len(spec.angles) for n in spec.expected)  # one part: light 11, full 42


def _input_tokens(mode: Mode, tokens: list[int]) -> int:
    """A lens call reads one part, so each round's lens calls read every part once; a skeptic call is costed at the
    largest part, since the estimate does not know which part its issue is in."""
    spec = MODES[mode]
    return sum(len(LENSES) * sum(tokens) + n * len(spec.angles) * max(tokens) for n in spec.expected)


def modes_for(parts: int) -> tuple[str, ...]:
    """A draft in several parts gets the light review only: a full review of several parts (up to 18 calls a part
    and round) could outrun DRAFT_REVIEW_JOB_TIMEOUT."""
    return tuple(MODES) if parts == 1 else ("light",)


def estimates(paper: str) -> list[dict]:
    tokens = [len(part) // 4 + PROMPT_TOKENS for part in split_parts(paper)]
    return [
        {
            "mode": m,
            "parts": len(tokens),
            "likely_calls": likely_calls(m, len(tokens)),
            "max_calls": max_calls(m, len(tokens)),
            "approx_input_tokens": _input_tokens(m, tokens),
        }
        for m in modes_for(len(tokens))
    ]


class Reply(BaseModel):
    issues: list[Any] = []


class Verdict(BaseModel):
    refuted: bool
    reason: str = ""


class ReviewFailed(Exception):
    pass


class Cancelled(Exception):
    pass


Progress = Callable[[str, int], Awaitable[bool]]  # (stage, calls done) -> False when the run was cancelled


@dataclass(frozen=True)
class Result:
    issues: list[dict]
    refuted: list[dict]
    counts: dict[str, int]
    model: str
    calls: int


async def _ask(llm, system: str, prompt: str, model: type[BaseModel]):
    try:
        return await ask_json(llm, system, prompt, model, retry=False)  # counted: one call, no retry
    except LLMError:  # LLMUnavailable is not one: it fails the run
        return None


async def _step(progress: Progress, stage: str, done: int) -> None:
    if not await progress(stage, done):
        raise Cancelled


def _out(issue: Issue, n: int) -> dict:
    return {
        "id": f"I-{n:02d}",
        "severity": issue.severity,
        "section": issue.section,
        "summary": issue.summary,
        "quote": issue.quote,
        "close_criterion": issue.close_criterion,
        "raised_by": list(issue.raised_by),
        "file": issue.place.file,
        "line": issue.place.line,
    }


def _shown(part: str, p: int, total: int) -> str:
    """The text a model reads for part `p` of `total`: the part alone, or with the part note when there are several."""
    return part if total == 1 else PART_NOTE.format(p=p, total=total) + part


def _stage(tag: str, n: int, lens: Lens, p: int, total: int) -> str:
    part = f", part {p} of {total}" if total > 1 else ""
    return f"{tag}Reviewer {n} of {len(LENSES)}: {lens.name}{part}"


def _home(quote: str, parts: list[str]) -> int:
    """The index of the first part the quote stands in. Always found: each issue's quote passed the check of the part
    that raised it, and a merged issue keeps one of those quotes. The 0 is a guard, never reached."""
    flat = [" ".join(part.split()) for part in parts]
    return next((i for i, text in enumerate(flat) if quote in text), 0)


async def _lenses(llm, progress: Progress, tag: str, parts: list[str], files, copied, calls: int):
    """Each lens reads each part once: (the issues that passed the checks, the drops by reason, failed calls, calls)."""
    found: list[Issue] = []
    dropped: Counter[str] = Counter()
    failed = 0
    for n, lens in enumerate(LENSES, 1):
        for p, part in enumerate(parts, 1):
            await _step(progress, _stage(tag, n, lens, p, len(parts)), calls)
            prompt = PROMPT_TEMPLATE.format(
                lens_name=lens.name, lens_focus=lens.focus, paper=_shown(part, p, len(parts))
            )
            reply = await _ask(llm, SYSTEM_PROMPT, prompt, Reply)
            calls += 1
            if reply is None:
                failed += 1
                continue
            for raw in reply.issues[:MAX_PER_REVIEWER]:
                issue, why = check_issue(raw, lens.id, files, copied, part)
                if issue is None:
                    dropped[f"dropped_{why}"] += 1
                else:
                    found.append(issue)
    return found, dropped, failed, calls


async def review(paper: str, files: Mapping[str, str], *, llm, progress: Progress, mode: Mode = "light") -> Result:
    spec = MODES[mode]
    parts = split_parts(paper)
    counts: Counter[str] = Counter()
    copied = grams([paper])
    seen: list[Place] = []  # every candidate span of an earlier round, refuted ones too
    survivors: list[Issue] = []
    refuted: list[dict] = []
    calls = 0
    for rnd in range(1, spec.rounds + 1):
        tag = f"Round {rnd} of {spec.rounds}: " if spec.rounds > 1 else ""
        found, dropped, failed, calls = await _lenses(llm, progress, tag, parts, files, copied, calls)
        counts.update(dropped)
        counts["reviewers_failed"] += failed
        if failed == len(LENSES) * len(parts) and rnd == 1:
            raise ReviewFailed("model_error")
        merged = merge(found, files)
        fresh = unseen(merged, seen)
        counts["dropped_seen"] += len(merged) - len(fresh)
        kept = fresh[:MAX_ISSUES]
        counts["over_cap"] += len(fresh) - len(kept)
        seen += [i.place for i in kept]
        won = 0
        for n, issue in enumerate(kept, 1):
            home = _home(issue.quote, parts)
            verdicts = []
            for a, angle in enumerate(spec.angles, 1):
                where = f"Skeptic {n} of {len(kept)}" + (
                    f", angle {a} of {len(spec.angles)}" if len(spec.angles) > 1 else ""
                )
                await _step(progress, f"{tag}{where}", calls)  # before every call: a cancel stops within one call
                prompt = VERIFY_TEMPLATE.format(
                    section=issue.section,
                    summary=issue.summary,
                    angle=angle,
                    quote=issue.quote,
                    paper=_shown(parts[home], home + 1, len(parts)),
                )
                verdict = await _ask(llm, VERIFY_SYSTEM_PROMPT, prompt, Verdict)
                calls += 1
                verdicts.append(verdict)
            counts["skeptics_failed"] += sum(v is None for v in verdicts)
            votes = [v for v in verdicts if v is not None and v.refuted]
            if len(votes) * 2 > len(spec.angles):  # a majority of the skeptics refuted it: 1 of 1, 2 of 3
                reason = votes[0].reason.strip()
                if not reason or len(reason.split()) > MAX_WORDS or reads_as_wording(reason, NO_REF, copied):
                    reason = MASKED_REASON  # model text is shown, so it passes the same D118 guard as an issue
                    counts["reasons_masked"] += 1
                refuted.append({"summary": issue.summary, "reason": reason})
            else:
                survivors.append(issue)
                won += 1
        counts["rounds_run"] = rnd
        if not kept or won == 0:  # a dry round (nothing new, or nothing survived) ends the loop
            break
    counts["refuted"] = len(refuted)
    counts["parts"] = len(parts)
    done = [_out(i, n) for n, i in enumerate(sorted(survivors, key=order(files)), 1)]
    return Result(done, refuted, dict(counts), getattr(llm, "model", "unknown"), calls)
