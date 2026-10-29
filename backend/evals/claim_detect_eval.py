"""Uncited-claim classifier gate: run claim_detect.classify with the default chat model over hand-written sentences
and compare each with its expected label. No paper, no database writes.

    docker compose exec api python -m evals.claim_detect_eval [--limit 10] [--out rows.jsonl]

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
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import claim_detect, llm_connections
from app.core.errors import DomainError
from app.db import SessionLocal
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm
from evals.run import EvalError

CONFIG = Path(__file__).with_name("claim_detect.yaml")


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(min_length=1)
    expected: Literal["claim", "not_claim"]


class Gates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accuracy_min: float = Field(ge=0, le=1)
    claim_recall_min: float = Field(ge=0, le=1)  # share of real claims flagged; a missed claim is the worse error


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
    accuracy: float
    claim_recall: float | None  # None: no claim case was run
    not_claim_accuracy: float | None
    errors: int  # model_error or call failure; counted wrong
    median_seconds: float


def _share(rows: list[dict]) -> float | None:
    return sum(r["correct"] for r in rows) / len(rows) if rows else None


def score(rows: list[dict]) -> Metrics:
    return Metrics(
        cases=len(rows),
        accuracy=_share(rows) or 0.0,
        claim_recall=_share([r for r in rows if r["expected"] == "claim"]),
        not_claim_accuracy=_share([r for r in rows if r["expected"] == "not_claim"]),
        errors=sum(r["error"] for r in rows),
        median_seconds=statistics.median(r["seconds"] for r in rows) if rows else 0.0,
    )


def _failed_gates(metrics: Metrics, gates: Gates) -> list[str]:
    failed = []
    if metrics.accuracy < gates.accuracy_min:
        failed.append(f"accuracy {metrics.accuracy:.2f} < {gates.accuracy_min}")
    if metrics.claim_recall is not None and metrics.claim_recall < gates.claim_recall_min:
        failed.append(f"claim recall {metrics.claim_recall:.2f} < {gates.claim_recall_min}")
    return failed


def passes(metrics: Metrics, gates: Gates) -> bool:
    return not _failed_gates(metrics, gates)


async def _classify(case: Case, llm) -> dict:
    start = time.perf_counter()
    row = {"sentence": case.sentence, "expected": case.expected, "prompt_version": claim_detect.PROMPT_VERSION}
    try:
        det = await claim_detect.classify(case.sentence, llm=llm)
    except (LLMError, LLMUnavailable) as exc:
        return {
            **row,
            "is_claim": None,
            "correct": False,
            "error": True,
            "reason": str(exc),
            "seconds": time.perf_counter() - start,
        }
    error = det.reason == claim_detect.MODEL_ERROR
    correct = not error and det.is_claim == (case.expected == "claim")
    return {
        **row,
        "is_claim": det.is_claim,
        "correct": correct,
        "error": error,
        "reason": det.reason,
        "seconds": time.perf_counter() - start,
    }


async def evaluate(cases: list[Case], llm, limit: int | None) -> tuple[Metrics, list[dict]]:
    rows = [await _classify(case, llm) for case in cases[:limit]]
    return score(rows), rows


async def execute(config: Config, llm, limit: int | None, out: Path | None) -> int:
    metrics, rows = await evaluate(config.cases, llm, limit)
    if out:
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"prompt_version={claim_detect.PROMPT_VERSION}", metrics)
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
