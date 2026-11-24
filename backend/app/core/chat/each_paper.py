"""M8.5 Ask each paper: a workspace question read paper by paper. Each paper gets its own six passages and its own
short record (found with cited passages, or absent: a real finding), then one answer is written from the records
(reduce_prepared). Plain workspace chat ranks every paper's passages together, so a few verbose papers crowd the rest
out and a paper that doesn't cover the question can't show at all (addendum §2b).

A record is an llm_outputs row of kind "paper_reading", which is also the cache: the same question over the same paper,
prompt version and model reuses it while all its passages still exist (a re-ingest replaces them)."""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import chat, claims
from app.core.chat.answer_provenance import snapshot
from app.core.chat.retrieval import RetrievedChunk, likely_papers, retrieve, searchable
from app.core.platform import prompts, skills
from app.core.workspaces import workspaces
from app.db import SessionLocal
from app.domain.errors import Conflict
from app.models import Chunk, LLMOutput, Paper, PaperStatus
from app.providers.base import LLMError, LLMUnavailable

PASSAGES = 6
MAP_CONCURRENCY = 2  # a local server answers one at a time anyway; a cloud one gets two
READING_PROMPT_VERSION = 1
OUTPUT_KIND = "paper_reading"
READING_SYSTEM, READING_TEMPLATE = prompts.load("paper_reading", READING_PROMPT_VERSION).split(chat.PROMPT_MARKER)
EACH_PAPER_PROMPT_VERSION = 1
EACH_PAPER_SYSTEM, EACH_PAPER_TEMPLATE = prompts.load("chat_each_paper", EACH_PAPER_PROMPT_VERSION).split(
    chat.PROMPT_MARKER
)

Status = Literal["found", "absent", "no_text", "model_error"]
_MARKER = re.compile(r"\[[PCN]\d+\]")
logger = logging.getLogger(__name__)


class _Reply(BaseModel):
    status: Literal["found", "absent"]
    answer: str = ""
    cites: list[str] = []


@dataclass(frozen=True)
class Reading:
    paper_id: uuid.UUID
    label: str
    status: Status
    answer: str
    cited: list[RetrievedChunk]
    output_id: uuid.UUID | None
    cached: bool
    low_confidence: bool = False  # found, but no cite among its passages


@dataclass(frozen=True)
class PaperTask:
    paper: Paper
    passages: list[RetrievedChunk]
    cached: Reading | None


@dataclass(frozen=True)
class Plan:
    workspace_id: uuid.UUID
    question: str
    tasks: list[PaperTask]
    papers_total: int  # ready papers in the workspace; more than len(tasks) when only the likeliest were read
    members: dict[uuid.UUID, Paper]
    skill: skills.SkillView | None


def _label(paper: Paper) -> str:
    return chat.source_label(paper)


async def _cached(
    session: AsyncSession, paper: Paper, question: str, model: str, passages: list[RetrievedChunk]
) -> Reading | None:
    """The newest record of this question, paper, prompt version and model read from exactly these passages."""
    query = (
        select(LLMOutput)
        .where(
            LLMOutput.kind == OUTPUT_KIND,
            LLMOutput.paper_id == paper.id,
            LLMOutput.question == question,
            LLMOutput.prompt_version == READING_PROMPT_VERSION,
            LLMOutput.model == model,
        )
        .order_by(LLMOutput.created_at.desc())
        .limit(1)
    )
    row = await session.scalar(query)
    # Read from exactly these passages: a skill's lens, a new chunk or a re-ingest gives others: read again.
    if row is None or row.source_chunks != [p.id for p in passages]:
        return None
    by_id = {c.id: c for c in await chat.chunk_sources(session, Chunk.id.in_(row.cited_chunks))}
    return _from_row(row, paper, by_id)


def _from_row(row: LLMOutput, paper: Paper | None, chunks: dict[uuid.UUID, RetrievedChunk]) -> Reading:
    content = json.loads(row.content)
    cited = [chunks[i] for i in row.cited_chunks if i in chunks]  # a re-ingest may have replaced some
    label = _label(paper) if paper is not None else "A paper no longer in the library"
    low = content["status"] == "found" and not cited
    return Reading(row.paper_id, label, content["status"], content["answer"], cited, row.id, True, low)


async def views_of(session: AsyncSession, rows: list[LLMOutput]) -> dict[uuid.UUID, Reading]:
    """Saved records by id, as a history shows them: each paper's label now and the cited passages still there."""
    if not rows:
        return {}
    papers = {p.id: p for p in await session.scalars(select(Paper).where(Paper.id.in_({r.paper_id for r in rows})))}
    wanted = {i for r in rows for i in r.cited_chunks}
    chunks = {c.id: c for c in await chat.chunk_sources(session, Chunk.id.in_(wanted))}
    return {row.id: _from_row(row, papers.get(row.paper_id), chunks) for row in rows}


async def plan(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    question: str,
    *,
    model: str,
    embedder=None,
    skill: skills.SkillView | None = None,
) -> Plan:
    """Which papers are read and from which passages, with no model call. Raises what workspace chat raises:
    NotFound, Conflict("workspace_empty" | "search_not_set_up" | "search_rebuilding" | "embedding_model_changed" |
    "workspace_not_indexed")."""
    members = {p.id: p for p in await workspaces.papers(session, workspace_id)}
    if not members:
        raise Conflict("workspace_empty")
    ready = [paper_id for paper_id, paper in members.items() if paper.status == PaperStatus.READY]
    embedder = await searchable(session, ready, embedder)
    if not await session.scalar(select(func.count(Chunk.embedding)).where(Chunk.paper_id.in_(ready))):
        raise Conflict("workspace_not_indexed")
    lens = chat._lens_of(skill)
    tasks = []
    for paper_id in await likely_papers(session, question, ready, embedder):
        paper = members[paper_id]
        lens_ids = [c.id for c in await chat.lens_sources(session, paper_id, lens)] if lens != chat.FULL_LENS else []
        passages = await retrieve(
            session, question, paper_ids=[paper_id], k=PASSAGES, embedder=embedder, chunk_ids=lens_ids or None
        )
        cached = await _cached(session, paper, question, model, passages) if passages else None
        tasks.append(PaperTask(paper, passages, cached))
    return Plan(workspace_id, question, tasks, len(ready), members, skill)


def _prompt(question: str, task: PaperTask) -> str:
    def where(p: RetrievedChunk) -> str:
        return "abstract only" if p.from_abstract else ", ".join(filter(None, [f"p. {p.page}", p.section]))

    passages = "\n\n".join(f"[P{i}] ({where(p)})\n{p.text}" for i, p in enumerate(task.passages, start=1))
    return READING_TEMPLATE.format(paper=task.paper.title, passages=passages, question=question)


async def _ask(question: str, task: PaperTask, llm, gate: asyncio.Semaphore) -> _Reply | None:
    """The model's record for one paper; None when it can't give one (unreachable after the retries, or invalid
    twice). No database work here: these run concurrently."""
    async with gate:
        try:
            return await claims._ask_with_retry(llm, READING_SYSTEM, _prompt(question, task), _Reply)
        except (LLMError, LLMUnavailable):
            return None
        except Exception:  # one paper's surprise must not end everyone's answer: it reads as that paper's model error
            logger.exception("reading %s for Ask each paper failed unexpectedly", task.paper.id)
            return None


async def _record(question: str, task: PaperTask, reply: _Reply | None, llm) -> Reading | None:
    """Saves the record (none for a model error) in a fresh session; None when the paper was deleted meanwhile."""
    paper, label = task.paper, _label(task.paper)
    if reply is None:
        return Reading(paper.id, label, "model_error", "", [], None, False)
    numbers = [int(c[1:]) for c in dict.fromkeys(reply.cites) if c[:1] == "P" and c[1:].isdigit()]
    kept = [n for n in numbers if 1 <= n <= len(task.passages)] if reply.status == "found" else []
    cited = [task.passages[n - 1] for n in kept]
    async with SessionLocal() as session:
        if await session.get(Paper, paper.id) is None:
            return None
        output = LLMOutput(
            paper_id=paper.id,
            kind=OUTPUT_KIND,
            question=question,
            content=json.dumps({"status": reply.status, "answer": reply.answer.strip(), "cites": reply.cites}),
            source_chunks=[p.id for p in task.passages],
            cited_chunks=[c.id for c in cited],
            source_snapshot=snapshot(task.passages, [f"C{n}" for n in kept]),
            model=getattr(llm, "model", "unknown"),
            connection_name=getattr(llm, "connection_name", None),
            prompt_version=READING_PROMPT_VERSION,
        )
        session.add(output)
        await session.commit()
        output_id = output.id
    low = reply.status == "found" and not cited
    return Reading(paper.id, label, reply.status, reply.answer.strip(), cited, output_id, False, low)


async def read_all(question: str, tasks: list[PaperTask], llm) -> AsyncIterator[Reading]:
    """Each paper's record as it lands: cached ones and papers without text first (no call), then the model's, at
    most MAP_CONCURRENCY at a time. A paper deleted meanwhile is left out."""
    asked = []
    for task in tasks:
        if task.cached is not None:
            yield task.cached
        elif not task.passages:
            yield Reading(task.paper.id, _label(task.paper), "no_text", "", [], None, False)
        else:
            asked.append(task)
    gate = asyncio.Semaphore(MAP_CONCURRENCY)
    pending = {asyncio.ensure_future(_ask(question, task, llm, gate)): task for task in asked}
    try:
        while pending:
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for future in done:
                task = pending.pop(future)
                reading = await _record(question, task, future.result(), llm)
                if reading is not None:
                    yield reading
    finally:
        for future in pending:  # the reader left mid-run: stop asking for the rest
            future.cancel()


def reduce_prepared(plan: Plan, readings: list[Reading]) -> chat.Prepared:
    """The answer's prompt from the records, in the plan's paper order. Its sources are the found records' cited
    passages, numbered C1..Cn, so citation pills, provenance and the answer check work as in chat."""
    by_paper = {r.paper_id: r for r in readings}
    ordered = [by_paper[t.paper.id] for t in plan.tasks if t.paper.id in by_paper]
    sources: list[RetrievedChunk] = []
    blocks, gaps = [], {"absent": [], "no_text": [], "model_error": []}
    for reading in ordered:
        if reading.status != "found":
            gaps[reading.status].append(reading.label)
            continue
        labels = "".join(f"[C{len(sources) + i}]" for i in range(1, len(reading.cited) + 1))
        sources += reading.cited
        # The record's own P/C labels mean nothing here: only its C numbers below do.
        answer = " ".join(_MARKER.sub("", reading.answer).split()).replace(" .", ".")
        blocks.append(f"### {reading.label}\n{answer} {labels}".rstrip())
    lines = [
        f"{heading}: {', '.join(names)}"
        for heading, names in (
            ("Not covered by", gaps["absent"]),
            ("No text to read in", gaps["no_text"]),
            ("Couldn't be read", gaps["model_error"]),
        )
        if names
    ]
    skipped = plan.papers_total - len(plan.tasks)
    if skipped:
        lines.append(f"Not read: {skipped} of {plan.papers_total} papers")
    prompt = EACH_PAPER_TEMPLATE.format(
        records="\n\n".join(blocks) or "No paper's passages answer the question.",
        gaps="\n".join(lines),
        question=plan.question,
    )
    return chat.Prepared(
        sources=sources,
        system=skills.compose(EACH_PAPER_SYSTEM, plan.skill),
        prompt=prompt,
        whole_paper=False,
        prompt_version=EACH_PAPER_PROMPT_VERSION,
        notes=[],
        readings=[r.output_id for r in ordered if r.output_id is not None],
        **chat._skill_fields(plan.skill),
    )
