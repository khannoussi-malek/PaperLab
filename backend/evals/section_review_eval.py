"""Section-review gate: run section_review.review with the default chat model over hand-written sections and check
that planted gaps are found, complete sections stay quiet and the lines are usable (not dropped). No model grades a
model; no paper, no database writes.

    docker compose exec api python -m evals.section_review_eval [--limit 5] [--out rows.jsonl]

Exit 0 pass, 1 fail (a gate missed, or no real model answer), 2 bad input.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core import llm_connections, section_review
from app.core.errors import DomainError
from app.core.section_rubrics import RUBRICS
from app.db import SessionLocal
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm
from evals.run import EvalError

CONFIG = Path(__file__).with_name("section_review.yaml")
COMPLETE_MAX_MISSING = 1


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    sentences: list[str] = Field(min_length=1)
    notes: list[str] = []
    expect_missing: list[list[str]]  # [] = a complete section; a group is met when any keyword is in a Missing line
    expect_note: str | None = None  # e.g. "N1": a Missing line should cite this note

    @field_validator("role")
    @classmethod
    def _reviewable(cls, role: str) -> str:
        if role not in RUBRICS:
            raise ValueError(f"unknown role {role!r}")
        return role


class Gates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_recall_min: float = Field(ge=0, le=1)  # planted gaps found
    complete_clean_min: float = Field(ge=0, le=1)  # complete sections with at most one Missing line
    usable_lines_min: float = Field(ge=0, le=1)  # kept / (kept + dropped)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gates: Gates
    cases: list[Case] = Field(min_length=1)


def load_config(path: Path) -> Config:
    try:
        return Config.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


@dataclass(frozen=True)
class Metrics:
    cases: int
    missing_recall: float | None  # None: no planted gap was run
    complete_clean: float | None  # None: no complete section was run
    usable_lines: float | None  # None: no line came back
    errors: int  # model_error or call failure
    median_seconds: float


def _share(hits: int, total: int) -> float | None:
    return hits / total if total else None


def score(rows: list[dict]) -> Metrics:
    ok = [r for r in rows if not r["error"]]
    planted = [r for r in rows if r["expect_missing"]]  # an errored case misses all its groups
    complete = [r for r in rows if not r["expect_missing"]]
    kept, dropped = sum(r["kept"] for r in ok), sum(r["dropped"] for r in ok)
    return Metrics(
        cases=len(rows),
        missing_recall=_share(sum(r["groups_met"] for r in planted), sum(len(r["expect_missing"]) for r in planted)),
        complete_clean=_share(
            sum(not r["error"] and r["missing"] <= COMPLETE_MAX_MISSING for r in complete), len(complete)
        ),
        usable_lines=_share(kept, kept + dropped),
        errors=sum(r["error"] for r in rows),
        median_seconds=statistics.median(r["seconds"] for r in rows) if rows else 0.0,
    )


def _failed_gates(metrics: Metrics, gates: Gates) -> list[str]:
    checks = [
        ("missing recall", metrics.missing_recall, gates.missing_recall_min),
        ("complete clean", metrics.complete_clean, gates.complete_clean_min),
        ("usable lines", metrics.usable_lines, gates.usable_lines_min),
    ]
    return [f"{name} {value:.2f} < {need}" for name, value, need in checks if value is not None and value < need]


def passes(metrics: Metrics, gates: Gates) -> bool:
    return not _failed_gates(metrics, gates)


async def _review(case: Case, llm) -> dict:
    start = time.perf_counter()
    row = {
        "role": case.role,
        "expect_missing": case.expect_missing,
        "prompt_version": section_review.PROMPT_VERSION,
        "kept": 0,
        "dropped": 0,
        "missing": 0,
        "groups_met": 0,
        "note_hit": None,
        "error": False,
    }
    try:
        result = await section_review.review(case.role, case.sentences, case.notes, llm=llm)
    except (LLMError, LLMUnavailable, section_review.ReviewFailed) as exc:
        return {**row, "error": True, "reason": str(exc), "seconds": time.perf_counter() - start}
    missing = [f for f in result.findings if f.kind == "missing"]
    text = " ".join(f.point.lower() for f in missing)
    wanted = case.expect_note
    return {
        **row,
        "kept": len(result.findings),
        "dropped": result.dropped,
        "missing": len(missing),
        "groups_met": sum(any(k.lower() in text for k in group) for group in case.expect_missing),
        "note_hit": None if wanted is None else any(f"{r.kind}{r.n}" == wanted for f in missing for r in f.refs),
        "points": [f"{f.kind}: {f.point}" for f in result.findings],
        "seconds": time.perf_counter() - start,
    }


async def evaluate(cases: list[Case], llm, limit: int | None) -> tuple[Metrics, list[dict]]:
    rows = [await _review(case, llm) for case in cases[:limit]]
    return score(rows), rows


async def execute(config: Config, llm, limit: int | None, out: Path | None) -> int:
    metrics, rows = await evaluate(config.cases, llm, limit)
    if out:
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"prompt_version={section_review.PROMPT_VERSION}", metrics)
    if metrics.errors == metrics.cases:
        print("FAIL: no real model answer (every call failed)")
        return 1
    failed = _failed_gates(metrics, config.gates)
    print("FAIL: " + "; ".join(failed) if failed else "PASS")
    return 1 if failed else 0


def _limit(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


async def _main(args) -> int:
    config = load_config(args.config)
    async with SessionLocal() as session:
        connection, model = await llm_connections.resolve(session, None)
        llm = build_llm(connection, model.name)
    return await execute(config, llm, args.limit, args.out)


def main() -> None:
    parser = argparse.ArgumentParser()  # a bad argument exits 2 by itself
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--limit", type=_limit)
    parser.add_argument("--out", type=Path)
    try:
        code = asyncio.run(_main(parser.parse_args()))
    except (EvalError, DomainError) as exc:
        print(f"bad input: {exc}", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
