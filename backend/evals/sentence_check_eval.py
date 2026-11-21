"""Answer-check gate (M34): run check_sentence with a chat model over planted answers whose passages are copied from
real chunks, and compare each sentence's verdict with the verdicts accepted for it. No retrieval, no database writes.

    docker compose exec api python -m evals.sentence_check_eval [--runs 3] [--model-id ID] [--out rows.jsonl]

Gate: every planted unsupported sentence is flagged in at least `unsupported_flagged_runs` runs (all of them, by
default), and every supported one passes in at least `supported_ok_runs`. Exit 0 pass, 1 fail, 2 bad input.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import llm_connections
from app.core.answer_check import CheckPassage, check_sentence
from app.core.answer_check_text import answer_sentences
from app.db import SessionLocal
from app.providers.llm import build_llm

CONFIG = Path(__file__).with_name("sentence_check.yaml")
Verdict = Literal["supported", "partially_supported", "not_supported", "not_addressed", "couldnt_check", "not_cited"]


class EvalError(Exception):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Passage(Strict):
    paper: str = Field(min_length=1)
    page: int | None = None  # None: the abstract
    section: str | None = None
    text: str = Field(min_length=1)


class Expect(Strict):
    role: Literal["supported", "unsupported", "uncited"]
    accept: list[Verdict] = Field(min_length=1)


class Case(Strict):
    id: str = Field(min_length=1)
    kind: Literal["true", "contradicted", "missing_number", "overstated", "second_passage", "uncited"]
    answer: str = Field(min_length=1)
    passages: dict[str, Passage]
    sentences: list[Expect] = Field(min_length=1)


class Gates(Strict):
    unsupported_flagged_runs: int = Field(default=3, ge=1)
    supported_ok_runs: int = Field(default=2, ge=1)


class Config(Strict):
    gates: Gates = Gates()
    cases: list[Case] = Field(min_length=1)


def load_config(path: Path) -> Config:
    try:
        return Config.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


def check_cases(config: Config) -> None:
    """Each case's expectations line up with its answer's sentences, and every cited label has a passage."""
    for case in config.cases:
        sentences = answer_sentences(case.answer)
        if len(sentences) != len(case.sentences):
            raise EvalError(f"{case.id}: {len(sentences)} sentences in the answer, {len(case.sentences)} expected")
        for sentence, expect in zip(sentences, case.sentences, strict=True):
            missing = [label for label in sentence.labels if label not in case.passages]
            if missing:
                raise EvalError(f"{case.id}: no passage for {', '.join(missing)}")
            if (expect.role == "uncited") != (not sentence.labels):
                raise EvalError(f"{case.id}: sentence {sentence.index} role {expect.role} but labels {sentence.labels}")


async def _verdicts(case: Case, llm) -> list[str]:
    out = []
    for sentence in answer_sentences(case.answer):
        if not sentence.labels:
            out.append("not_cited")
            continue
        passages = [CheckPassage(label, p.paper, p.page, p.section, p.text, False)
                    for label in sentence.labels for p in [case.passages[label]]]
        out.append((await check_sentence(llm, sentence.text, passages)).verdict)
    return out


@dataclass
class Result:
    passed: bool
    failures: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    seconds_per_sentence: float | None = None


def _gate(config: Config, rows: list[dict], runs: int) -> list[str]:
    need = {"unsupported": min(config.gates.unsupported_flagged_runs, runs),
            "supported": min(config.gates.supported_ok_runs, runs), "uncited": runs}
    failures = []
    for case in config.cases:
        for index, expect in enumerate(case.sentences):
            mine = [r for r in rows if r["case"] == case.id and r["sentence"] == index]
            ok = sum(r["ok"] for r in mine)
            if ok < need[expect.role]:
                verdicts = ", ".join(r["verdict"] for r in mine)
                failures.append(f"{case.id} sentence {index} ({expect.role}): {ok}/{runs} right [{verdicts}]")
    return failures


async def execute(config: Config, llm, runs: int) -> Result:
    check_cases(config)
    rows, checked, started = [], 0, time.perf_counter()
    for run in range(runs):
        for case in config.cases:
            for index, (verdict, expect) in enumerate(zip(await _verdicts(case, llm), case.sentences, strict=True)):
                checked += verdict != "not_cited"
                rows.append({"run": run, "case": case.id, "kind": case.kind, "sentence": index, "role": expect.role,
                             "verdict": verdict, "ok": verdict in expect.accept})
    failures = _gate(config, rows, runs)
    per = (time.perf_counter() - started) / checked if checked else None
    return Result(passed=not failures, failures=failures, rows=rows, seconds_per_sentence=per)


async def model_llm(model_id: uuid.UUID | None):
    async with SessionLocal() as session:
        connection, model = await llm_connections.resolve(session, model_id)
        return build_llm(connection, model.name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate for answer checks (M34).")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model-id", type=uuid.UUID)
    parser.add_argument("--out", type=Path)
    return parser


async def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        check_cases(config)
    except EvalError as exc:
        print(f"bad input: {exc}", file=sys.stderr)
        return 2
    llm = await model_llm(args.model_id)
    result = await execute(config, llm, max(1, args.runs))
    if args.out:
        args.out.write_text("".join(json.dumps(row) + "\n" for row in result.rows))
    model = getattr(llm, "model", "unknown")
    per = f"{result.seconds_per_sentence:.1f} s per checked sentence" if result.seconds_per_sentence else "no checks"
    print(f"model {model} · {args.runs} runs · {len(config.cases)} cases · {per}")
    for failure in result.failures:
        print(f"MISS {failure}")
    print("PASS" if result.passed else "FAIL")
    return 0 if result.passed else 1


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
