"""Diagram gate: run diagram.generate with the default chat model over hand-written descriptions, then check the code
passes the guard, compiles with real Tectonic, and labels every node the description names without inventing others.
No model grades a model; no paper, no database writes.

    docker compose exec api python -m evals.diagram_eval [--limit 5] [--out rows.jsonl]

Exit 0 pass, 1 fail (a gate missed, or no real model answer), 2 bad input (incl. no Tectonic binary).
"""

import argparse
import asyncio
import json
import shutil
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.core import diagram, diagram_compile, diagram_tikz, llm_connections
from app.core.errors import DomainError
from app.db import SessionLocal
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm
from evals.run import EvalError

CONFIG = Path(__file__).with_name("diagram.yaml")
CompileFn = Callable[[list[str], str], Awaitable[bool]]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=diagram.MAX_DESCRIPTION)
    nodes: list[str] = Field(min_length=1)  # each must appear (case-insensitive substring) among the node labels


class Gates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compile_rate_min: float = Field(ge=0, le=1)  # guard clean and compiled, over all cases
    nodes_present_min: float = Field(ge=0, le=1)  # named nodes found, over all named nodes
    invented_label_rate_max: float = Field(ge=0, le=1)  # labels with a word the description never says


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gates: Gates
    cases: list[Case] = Field(min_length=1)


def load_config(path: Path) -> Config:
    try:
        return Config.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


def require_tectonic() -> None:
    if not (shutil.which(settings.tectonic_bin) or Path(settings.tectonic_bin).is_file()):
        raise EvalError(f"no Tectonic binary at {settings.tectonic_bin!r} (scripts/tectonic-dev.sh, or run in the api)")


async def real_compile(libraries: list[str], picture: str) -> bool:
    return (await diagram_compile.preview(libraries, picture)).ok


@dataclass(frozen=True)
class Metrics:
    cases: int
    compile_rate: float
    nodes_present: float
    invented_label_rate: float | None  # None: no label came back
    errors: int  # model_error or call failure
    median_seconds: float


def score(rows: list[dict]) -> Metrics:
    labels = sum(r["labels"] for r in rows)
    return Metrics(
        cases=len(rows),
        compile_rate=sum(r["compiled"] for r in rows) / len(rows),
        nodes_present=sum(r["nodes_found"] for r in rows) / sum(r["nodes"] for r in rows),
        invented_label_rate=sum(len(r["invented"]) for r in rows) / labels if labels else None,
        errors=sum(r["error"] for r in rows),
        median_seconds=statistics.median(r["seconds"] for r in rows),
    )


def _failed_gates(metrics: Metrics, gates: Gates) -> list[str]:
    failed = [
        f"{name} {value:.2f} < {need}"
        for name, value, need in [
            ("compile rate", metrics.compile_rate, gates.compile_rate_min),
            ("nodes present", metrics.nodes_present, gates.nodes_present_min),
        ]
        if value < need
    ]
    rate = metrics.invented_label_rate
    if rate is not None and rate > gates.invented_label_rate_max:
        failed.append(f"invented label rate {rate:.2f} > {gates.invented_label_rate_max}")
    return failed


def passes(metrics: Metrics, gates: Gates) -> bool:
    return not _failed_gates(metrics, gates)


async def _draw(case: Case, llm, compile_fn: CompileFn) -> dict:
    start = time.perf_counter()
    row = {"description": case.description, "nodes": len(case.nodes), "prompt_version": diagram.PROMPT_VERSION}
    empty = {"nodes_found": 0, "labels": 0, "invented": [], "guard": [], "compiled": False}
    try:
        got = await diagram.generate(case.description, llm=llm)
    except (LLMError, LLMUnavailable, diagram.DiagramFailed) as exc:
        return {**row, **empty, "error": True, "reason": str(exc), "seconds": time.perf_counter() - start}
    labels = [label.lower() for label in diagram_tikz.node_labels(got.picture)]
    return {
        **row,
        "error": False,
        "nodes_found": sum(any(n.lower() in label for label in labels) for n in case.nodes),
        "labels": len(labels),
        "invented": got.labels_not_in_description,
        "guard": got.errors,
        "compiled": not got.errors and await compile_fn(got.libraries, got.picture),
        "code": got.picture,
        "seconds": time.perf_counter() - start,
    }


async def evaluate(cases: list[Case], llm, limit: int | None, compile_fn: CompileFn) -> tuple[Metrics, list[dict]]:
    rows = [await _draw(case, llm, compile_fn) for case in cases[:limit]]
    return score(rows), rows


async def execute(config: Config, llm, limit: int | None, out: Path | None, compile_fn: CompileFn) -> int:
    metrics, rows = await evaluate(config.cases, llm, limit, compile_fn)
    if out:
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"prompt_version={diagram.PROMPT_VERSION}", metrics)
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
    require_tectonic()
    async with SessionLocal() as session:
        connection, model = await llm_connections.resolve(session, None)
        llm = build_llm(connection, model.name)
    return await execute(config, llm, args.limit, args.out, real_compile)


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
