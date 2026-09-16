"""Answer eval: is chat's answer right, grounded in a passage it cites, and how fast, under each context config.

    docker compose exec api python -m evals.answers --label today
    docker compose exec api python -m evals.answers --summarize evals/results/today.jsonl

Every case in evals/answers.yaml is asked of the default model (chosen in Settings) under each config:
- none: no passages, only the paper's name. Shows which answers the model already knows without reading.
- retrieval: chat as it is.
- whole: every paper sent whole, with a context big enough to hold it.

`--with-paper-notes` saves the file's paper_notes on their papers before every question (rolled back after), to
see whether a reader's notes change ordinary answers. One JSONL row per answer goes to evals/results/<label>.jsonl,
then a summary is printed. A rerun only asks what is
missing or failed. Manual, never in CI. Exits 2 on a malformed cases file, an ambiguous or unknown paper, or ground
truth that isn't on its page; 1 when the model or a paper can't answer.
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Annotated, Literal
from unittest.mock import patch

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import settings
from app.core import chat, llm_connections
from app.core.errors import DomainError
from app.core.notes import normalize_quote
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, Note, Provenance, note_anchors
from app.providers import embedding
from app.providers import llm as llm_provider
from app.providers.base import LLM, LLMError, LLMUnavailable
from evals.answer_check import citation_problems
from evals.run import EvalError, Expected, is_hit, normalize, resolve_papers

CASES = Path(__file__).with_name("answers.yaml")
RESULTS = Path(__file__).with_name("results")
CONFIGS = ("none", "retrieval", "whole")
KINDS = ("fact", "overview", "followup", "notes", "refusal")
# Only these can be known without reading: a follow-up or a note's answer isn't in anything the model was trained on.
MEMORY_CHECKED = {"fact", "overview"}
# Every eval paper is under 100k characters (~25k tokens), so `whole` sends each one whole; 32k tokens holds that
# plus the answer, and qwen3:8b supports it.
WHOLE_PAPER_CHARS = 100_000
WHOLE_NUM_CTX = 32_768
NO_PASSAGES_SYSTEM = "Answer the question about the named research paper from what you already know. Be concise."
REQUIRED_FIELD = {"fact": "evidence", "followup": "before", "notes": "note"}
# A refusal case's answer is correct when it says the paper doesn't cover the question, in any of these words.
REFUSALS = [
    "not mentioned", "not specified", "not provided", "not stated", "not reported", "not discussed", "not included",
    "not covered", "not available", "no information", "cannot be determined", "cannot determine", "can't determine",
    "does not mention", "does not specify", "does not provide", "does not report", "does not state",
    "does not include", "does not contain", "do not mention", "do not specify", "do not provide", "do not include",
    "do not contain", "doesn't mention", "doesn't specify", "doesn't provide", "doesn't report", "doesn't include",
    "don't mention", "don't provide", "isn't specified", "isn't mentioned", "not in the sources",
    "cannot be answered", "can't be answered", "cannot answer", "can't answer", "no mention",
    "not explicitly provided", "not explicitly stated", "not explicitly mentioned",
]
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")

Scratch = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class NoteFixture(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)  # text on that page; the note is anchored to it
    body: str = Field(min_length=1)
    provenance: Literal["human", "llm"] = "human"  # llm: a note saved from an AI answer


class PaperNotes(BaseModel):
    paper: str = Field(min_length=1)  # a title prefix, as in a case
    notes: list[NoteFixture] = Field(min_length=1)


class Case(BaseModel):
    id: str = Field(min_length=1)
    kind: Literal["fact", "overview", "followup", "notes", "refusal"]
    paper: str = Field(min_length=1)  # a title prefix, as in questions.yaml
    question: str = Field(min_length=1)
    points: list[Annotated[list[str], Field(min_length=1)]] = []  # a point is met by any phrasing; refusal: REFUSALS
    need: int | None = Field(default=None, ge=1)  # points an answer must hit; all of them when omitted
    evidence: list[Expected] = []  # a passage the answer cites must hold one of these
    before: str | None = None  # followup: the question this one follows
    note: NoteFixture | None = None  # notes: saved before asking, always rolled back

    @model_validator(mode="after")
    def fits_kind(self):
        if not self.points and self.kind == "refusal":
            self.points = [REFUSALS]
        field = "points" if not self.points else REQUIRED_FIELD.get(self.kind)
        if field and not getattr(self, field):
            raise ValueError(f"{self.id}: {self.kind} needs {field}")
        if self.need is not None and self.need > len(self.points):
            raise ValueError(f"{self.id}: need is more than the {len(self.points)} points")
        return self

    @property
    def required(self) -> int:
        return self.need or len(self.points)


class CaseFile(BaseModel):
    cases: list[Case] = Field(min_length=1)
    paper_notes: list[PaperNotes] = []  # saved before every question on their paper with --with-paper-notes


def load(path: Path) -> CaseFile:
    try:
        loaded = CaseFile.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise EvalError(f"{path}: {exc}") from exc
    ids = [case.id for case in loaded.cases]
    if duplicate := next((i for i in ids if ids.count(i) > 1), None):
        raise EvalError(f"{path}: duplicate case id {duplicate!r}")
    return loaded


def load_cases(path: Path) -> list[Case]:
    return load(path).cases


def _plain(text: str) -> str:
    """Lowercase, single spaces, and 20,574 as 20574, so an answer's formatting can't hide a match."""
    return _THOUSANDS.sub("", normalize(text))


def mentions(text: str, phrasing: str) -> bool:
    """Whether `text` says `phrasing` as whole words: "cli" isn't found in "client"."""
    return re.search(rf"(?<!\w){re.escape(_plain(phrasing))}(?!\w)", _plain(text)) is not None


def points_hit(text: str, points: list[list[str]]) -> int:
    return sum(any(mentions(text, phrasing) for phrasing in point) for point in points)


def is_correct(text: str, case: Case) -> bool:
    return points_hit(text, case.points) >= case.required


def grounded(content: str, sources: list[RetrievedChunk], evidence: list[Expected]) -> bool | None:
    """Whether a passage the answer cites holds the evidence. None for a case without evidence."""
    if not evidence:
        return None
    return is_hit([sources[i - 1] for i in chat.parse_citations(content, len(sources))], evidence)


async def _chunk_holding(session: AsyncSession, paper_id: uuid.UUID, page: int, phrase: str):
    """The first chunk on `page` holding `phrase`, compared as run.is_hit compares; None when there is none."""
    query = select(Chunk.text, Chunk.bbox).where(Chunk.paper_id == paper_id, Chunk.page == page)
    rows = await session.execute(query.order_by(Chunk.ordinal))
    return next((row for row in rows if normalize(phrase) in normalize(row.text)), None)


async def check_ground_truth(
    session: AsyncSession, cases: list[Case], paper_ids: dict[str, uuid.UUID], paper_notes: Iterable[PaperNotes] = ()
) -> list[str]:
    """Every evidence phrase and note quote that isn't on its page. A typo there would score right answers wrong."""
    problems = []
    for case in cases:
        for expected in case.evidence:
            if await _chunk_holding(session, paper_ids[case.paper], expected.page, expected.contains) is None:
                problems.append(f"{case.id}: evidence {expected.contains!r} isn't on page {expected.page}")
        note = case.note
        if note and await _chunk_holding(session, paper_ids[case.paper], note.page, note.quote) is None:
            problems.append(f"{case.id}: note quote {note.quote!r} isn't on page {note.page}")
    for block in paper_notes:
        for note in block.notes:
            if await _chunk_holding(session, paper_ids[block.paper], note.page, note.quote) is None:
                problems.append(f"{block.paper}: note quote {note.quote!r} isn't on page {note.page}")
    return problems


async def add_note(session: AsyncSession, paper_id: uuid.UUID, fixture: NoteFixture) -> None:
    """The case's note, anchored like a highlight on its quote. Flushed, never committed."""
    anchor = await _chunk_holding(session, paper_id, fixture.page, fixture.quote)
    note = Note(body=fixture.body, provenance=Provenance(fixture.provenance))
    session.add(note)
    await session.flush()
    await session.execute(
        insert(note_anchors).values(
            note_id=note.id, paper_id=paper_id, page=fixture.page, bbox=anchor.bbox,
            quoted_text=normalize_quote(fixture.quote),
        )
    )


@asynccontextmanager
async def rolled_back(engine: AsyncEngine):
    """A session whose writes, commits included, are all rolled back when it closes."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                yield session
        finally:
            await transaction.rollback()


@contextmanager
def limits(config: str) -> Iterator[None]:
    """`whole` raises the whole-paper cutoff and Ollama's context while it runs; the other configs change nothing."""
    if config != "whole":
        yield
        return
    with (
        patch.object(chat, "SMALL_PAPER_CHARS", WHOLE_PAPER_CHARS),
        patch.object(llm_provider, "OLLAMA_NUM_CTX", WHOLE_NUM_CTX),
    ):
        yield


async def prepare_case(
    session: AsyncSession, case: Case, config: str, paper_id: uuid.UUID, embedder, notes: Iterable[NoteFixture] = ()
) -> chat.Prepared:
    if config == "none":
        prompt = f"Paper: {case.paper}\n\nQuestion: {case.question}"
        return chat.Prepared(sources=[], system=NO_PASSAGES_SYSTEM, prompt=prompt, whole_paper=False)
    for note in [*notes, *([case.note] if case.note else [])]:
        await add_note(session, paper_id, note)
    scope, thread = chat.Scope(paper_id=paper_id), None
    if case.before:
        # The earlier question is prepared but never asked: a follow-up carries its passages, not its answer.
        earlier = await chat.prepare(session, scope, case.before, embedder)
        thread = chat.Thread(questions=[case.before], source_ids=[s.id for s in earlier.sources])
    return await chat.prepare(session, scope, case.question, embedder, thread=thread)


@dataclass(frozen=True)
class Streamed:
    content: str
    ttft: float | None  # seconds until the first visible text; None when none arrived
    total: float
    error: str | None = None


async def stream(llm: LLM, system: str, prompt: str) -> Streamed:
    start, parts, ttft = time.perf_counter(), [], None
    try:
        async for text in llm.stream(system, prompt):
            if ttft is None and text.strip():
                ttft = time.perf_counter() - start
            parts.append(text)
    except (LLMError, LLMUnavailable) as exc:
        return Streamed("".join(parts), ttft, time.perf_counter() - start, str(exc))
    return Streamed("".join(parts), ttft, time.perf_counter() - start)


def score(
    label: str, config: str, case: Case, repeat: int, prepared: chat.Prepared, answer: Streamed, model: str,
    first_on_paper: bool,
) -> dict:
    ok = answer.error is None
    return {
        "label": label, "config": config, "case": case.id, "kind": case.kind, "paper": case.paper,
        "repeat": repeat, "model": model,
        "correct": is_correct(answer.content, case) if ok else None,
        "points": points_hit(answer.content, case.points), "need": case.required, "of": len(case.points),
        "grounded": grounded(answer.content, prepared.sources, case.evidence) if ok else None,
        "citations_valid": not citation_problems(answer.content, prepared) if ok and config != "none" else None,
        "ttft": answer.ttft, "total": answer.total, "prompt_chars": len(prepared.system) + len(prepared.prompt),
        "sources": len(prepared.sources), "whole_paper": prepared.whole_paper, "notes": len(prepared.notes),
        "first_on_paper": first_on_paper, "error": answer.error, "content": answer.content,
    }


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def rescore(path: Path, cases: list[Case]) -> int:
    """Recomputes, in place, what depends only on an answer's text (`correct`, `points`), after a case's phrasings
    change. `grounded` needs the passages the answer saw, which aren't stored. Returns the rows whose score changed."""
    by_id = {case.id: case for case in cases}
    rows, changed = read_rows(path), 0
    for row in rows:
        case = by_id.get(row["case"])
        if case is None or row["error"] is not None:
            continue
        before = (row["correct"], row["points"])
        row.update(points=points_hit(row["content"], case.points), need=case.required, of=len(case.points))
        row["correct"] = row["points"] >= case.required
        changed += before != (row["correct"], row["points"])
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return changed


def completed(path: Path) -> set[tuple[str, str, str, int]]:
    """(label, config, case, repeat) of every answer already written without an error."""
    if not path.exists():
        return set()
    return {(r["label"], r["config"], r["case"], r["repeat"]) for r in read_rows(path) if r["error"] is None}


async def evaluate(
    cases: list[Case], *, paper_ids: dict[str, uuid.UUID], configs: Iterable[str], repeats: int, label: str,
    out: Path, scratch: Scratch, llm: LLM, embedder, paper_notes: Iterable[PaperNotes] = (),
) -> None:
    """Ask every pending (config, case, repeat) and append its scored row to `out`.

    A paper's questions run back to back, so a whole-paper prompt can reuse the model's cache of the same paper.
    """
    done = completed(out)
    notes_on = {block.paper: block.notes for block in paper_notes}
    out.parent.mkdir(parents=True, exist_ok=True)
    for config in configs:
        pending = [
            (case, repeat)
            for case in sorted(cases, key=lambda c: c.paper)
            for repeat in range(1 if config == "none" else repeats)
            if (config != "none" or case.kind in MEMORY_CHECKED) and (label, config, case.id, repeat) not in done
        ]
        if not pending:
            continue
        with limits(config):
            warm_up = await stream(llm, "Reply with OK.", "OK")  # loads the model at this context, off the clock
            if warm_up.error:
                raise LLMUnavailable(warm_up.error)
            asked: set[str] = set()
            for case, repeat in pending:
                async with scratch() as session:
                    notes = notes_on.get(case.paper, [])
                    prepared = await prepare_case(session, case, config, paper_ids[case.paper], embedder, notes)
                answer = await stream(llm, prepared.system, prepared.prompt)
                row = score(label, config, case, repeat, prepared, answer, llm.model, case.paper not in asked)
                asked.add(case.paper)
                with out.open("a") as file:
                    file.write(json.dumps(row) + "\n")


def _mean(values: Iterable[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known), 2) if known else None


def _median(values: Iterable[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(statistics.median(known), 1) if known else None


def summary(rows: list[dict]) -> list[dict]:
    """Per label, config and kind, over answers that didn't fail. `correct_unseen` leaves out every case the `none`
    config answered correctly: passages can't be credited for what the model already knew. `coverage` is the share of
    key points hit, which still shows a better summary when both miss the `need` bar."""
    known = {r["case"] for r in rows if r["config"] == "none" and r["correct"]}
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["label"], r["config"], r["kind"]), []).append(r)
    result = []
    for (label, config, kind), group in groups.items():
        ok = [r for r in group if r["error"] is None]
        result.append({
            "label": label, "config": config, "kind": kind, "answers": len(ok), "errors": len(group) - len(ok),
            "correct": _mean(r["correct"] for r in ok),
            "correct_unseen": _mean(r["correct"] for r in ok if r["case"] not in known),
            "coverage": _mean(r["points"] / r["of"] for r in ok),
            "grounded": _mean(r["grounded"] for r in ok),
            "citations_valid": _mean(r["citations_valid"] for r in ok),
            # Timings count a question's first ask only: a repeat reuses the model's cache of the identical prompt.
            "median_ttft": _median(r["ttft"] for r in ok if r["repeat"] == 0),
            # A whole-paper prompt pays for reading the paper once; later questions on it reuse the model's cache.
            "median_ttft_first": _median(r["ttft"] for r in ok if r["first_on_paper"]),
            "median_total": _median(r["total"] for r in ok if r["repeat"] == 0),
            "median_prompt_chars": _median(r["prompt_chars"] for r in ok),
        })
    order = {name: i for i, name in enumerate((*KINDS, *CONFIGS))}
    return sorted(result, key=lambda s: (s["label"], order.get(s["kind"], 99), order.get(s["config"], 99)))


COLUMNS = {
    "label": "label", "config": "config", "kind": "kind", "answers": "answers", "errors": "errors",
    "correct": "correct", "correct_unseen": "correct, not known before", "coverage": "key points hit",
    "grounded": "cites the evidence", "citations_valid": "citations valid", "median_ttft": "s to first word",
    "median_ttft_first": "s to first word, paper's first question", "median_total": "s total",
    "median_prompt_chars": "prompt chars",
}
RATES = {"correct", "correct_unseen", "coverage", "grounded", "citations_valid"}


def format_summary(stats: list[dict]) -> str:
    def cell(key: str, value) -> str:
        if value is None:
            return "–"
        return f"{value:.0%}" if key in RATES else str(value)

    lines = ["| " + " | ".join(COLUMNS.values()) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(cell(key, s[key]) for key in COLUMNS) + " |" for s in stats]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score chat answers from the default model under each config.")
    parser.add_argument("--label", default="today", help="names this run's rows and results file")
    parser.add_argument("--configs", default=",".join(CONFIGS), help=f"comma-separated, from {', '.join(CONFIGS)}")
    parser.add_argument("--repeats", type=int, default=3, help="answers per case and config; `none` asks once")
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--kinds", help=f"comma-separated, from {', '.join(KINDS)}")
    parser.add_argument("--with-paper-notes", action="store_true", help="save the file's paper_notes first")
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--out", type=Path, help="default: evals/results/<label>.jsonl")
    parser.add_argument("--summarize", nargs="+", type=Path, metavar="JSONL", help="summarize these files and exit")
    parser.add_argument("--rescore", nargs="+", type=Path, metavar="JSONL", help="rescore these files in place, exit")
    parser.add_argument("--database-url", default=settings.database_url)
    return parser.parse_args(argv)


def select_cases(cases: list[Case], only: str | None, kinds: str | None) -> list[Case]:
    ids = only.split(",") if only else None
    wanted_kinds = kinds.split(",") if kinds else None
    if ids and (unknown := sorted(set(ids) - {case.id for case in cases})):
        raise EvalError(f"unknown case ids: {', '.join(unknown)}")
    if wanted_kinds and (unknown := sorted(set(wanted_kinds) - set(KINDS))):
        raise EvalError(f"unknown kinds: {', '.join(unknown)}")
    return [case for case in cases if (not ids or case.id in ids) and (not wanted_kinds or case.kind in wanted_kinds)]


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.summarize:
        print(format_summary(summary([row for path in args.summarize for row in read_rows(path)])))
        return 0
    if args.rescore:
        cases = load_cases(args.cases)
        for path in args.rescore:
            print(f"{path}: {rescore(path, cases)} answers rescored differently")
        return 0
    out = args.out or RESULTS / f"{args.label}.jsonl"
    engine = create_async_engine(args.database_url)
    scratch = partial(rolled_back, engine)
    try:
        configs = args.configs.split(",")
        if unknown := sorted(set(configs) - set(CONFIGS)):
            raise EvalError(f"unknown configs: {', '.join(unknown)}")
        loaded = load(args.cases)
        cases = select_cases(loaded.cases, args.only, args.kinds)
        paper_notes = loaded.paper_notes if args.with_paper_notes else []
        async with scratch() as session:
            paper_ids = await resolve_papers(session, [*cases, *paper_notes])
            problems = await check_ground_truth(session, cases, paper_ids, paper_notes)
            connection, model = await llm_connections.resolve(session, None)
            llm = llm_provider.build_llm(connection, model.name)
        if problems:
            raise EvalError("ground truth isn't in the papers:\n  " + "\n  ".join(problems))
        await evaluate(
            cases, paper_ids=paper_ids, configs=configs, repeats=args.repeats, label=args.label, out=out,
            scratch=scratch, llm=llm, embedder=embedding.load(), paper_notes=paper_notes,
        )
    except EvalError as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2
    except (DomainError, LLMError, LLMUnavailable) as exc:
        print(f"answer eval failed: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(format_summary(summary(read_rows(out))))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
