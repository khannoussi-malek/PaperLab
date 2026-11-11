"""Whole-draft review, the model half (S2P B7). Three fixed lenses read the whole paper, their issues are checked,
merged and sorted, and skeptics try to refute each issue. Light: 1 skeptic, 1 round, at most 11 calls. Full: 3 angled
skeptics, up to 2 rounds, stop early when a round is dry, at most 54 calls. An issue is dropped when a majority of its
skeptics refute it. It judges and never writes wording (D118). The pure half is draft_review_issues."""

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.core import prompts
from app.core.draft_review_issues import MAX_WORDS, NO_REF, Issue, Place, check_issue, merge, order, unseen
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


def max_calls(mode: Mode) -> int:
    spec = MODES[mode]
    return spec.rounds * (len(LENSES) + MAX_ISSUES * len(spec.angles))  # light 11, full 54


def likely_calls(mode: Mode) -> int:
    spec = MODES[mode]
    return sum(len(LENSES) + n * len(spec.angles) for n in spec.expected)  # light 11, full 42 (the card: about 44)


def estimates(paper_chars: int) -> list[dict]:
    per_call = paper_chars // 4 + PROMPT_TOKENS
    return [
        {
            "mode": m,
            "likely_calls": likely_calls(m),
            "max_calls": max_calls(m),
            "approx_input_tokens": per_call * likely_calls(m),
        }
        for m in MODES
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


async def review(paper: str, files: Mapping[str, str], *, llm, progress: Progress, mode: Mode = "light") -> Result:
    spec = MODES[mode]
    counts: Counter[str] = Counter()
    copied = grams([paper])
    seen: list[Place] = []  # every candidate span of an earlier round, refuted ones too
    survivors: list[Issue] = []
    refuted: list[dict] = []
    calls = 0
    for rnd in range(1, spec.rounds + 1):
        tag = f"Round {rnd} of {spec.rounds}: " if spec.rounds > 1 else ""
        found: list[Issue] = []
        failed = 0
        for n, lens in enumerate(LENSES, 1):
            await _step(progress, f"{tag}Reviewer {n} of {len(LENSES)}: {lens.name}", calls)
            prompt = PROMPT_TEMPLATE.format(lens_name=lens.name, lens_focus=lens.focus, paper=paper)
            reply = await _ask(llm, SYSTEM_PROMPT, prompt, Reply)
            calls += 1
            if reply is None:
                failed += 1
                continue
            for raw in reply.issues[:MAX_PER_REVIEWER]:
                issue, why = check_issue(raw, lens.id, files, copied, paper)
                if issue is None:
                    counts[f"dropped_{why}"] += 1
                else:
                    found.append(issue)
        counts["reviewers_failed"] += failed
        if failed == len(LENSES) and rnd == 1:
            raise ReviewFailed("model_error")
        merged = merge(found, files)
        fresh = unseen(merged, seen)
        counts["dropped_seen"] += len(merged) - len(fresh)
        kept = fresh[:MAX_ISSUES]
        counts["over_cap"] += len(fresh) - len(kept)
        seen += [i.place for i in kept]
        won = 0
        for n, issue in enumerate(kept, 1):
            verdicts = []
            for a, angle in enumerate(spec.angles, 1):
                where = f"Skeptic {n} of {len(kept)}" + (
                    f", angle {a} of {len(spec.angles)}" if len(spec.angles) > 1 else ""
                )
                await _step(progress, f"{tag}{where}", calls)  # before every call: a cancel stops within one call
                prompt = VERIFY_TEMPLATE.format(
                    section=issue.section, summary=issue.summary, angle=angle, quote=issue.quote, paper=paper
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
    done = [_out(i, n) for n, i in enumerate(sorted(survivors, key=order(files)), 1)]
    return Result(done, refuted, dict(counts), getattr(llm, "model", "unknown"), calls)
