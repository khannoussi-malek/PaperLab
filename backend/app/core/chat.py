"""Single-paper chat: choose the sources, build the prompt, store answers.

Never writes notes: an answer becomes a note only through notes.promote_llm_fragment.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import prompts
from app.core.errors import Conflict
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk, _to_chunk, retrieve
from app.models import Chunk, LLMOutput, Paper, PaperStatus

CHAT_PROMPT_VERSION = 1
# The file holds the system prompt, then the user prompt template after the marker line.
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat", CHAT_PROMPT_VERSION).split("\n<!-- prompt -->\n")
# ponytail: characters stand in for tokens. Revisit with the eval numbers or a model's real context size.
SMALL_PAPER_CHARS = 24_000
RETRIEVE_K = 8
_CITATION = re.compile(r"\[C(\d+)\]")
_SOURCE_COLUMNS = (Chunk.id, Chunk.paper_id, Chunk.page, Chunk.section_title, Chunk.bbox, Chunk.text)


@dataclass(frozen=True)
class Prepared:
    sources: list[RetrievedChunk]  # C{i} is sources[i-1]
    system: str
    prompt: str
    whole_paper: bool


@dataclass(frozen=True)
class Answer:
    output: LLMOutput
    sources: list[RetrievedChunk | None]  # None: a re-ingest replaced that chunk


async def _chunk_sources(session: AsyncSession, *where) -> list[RetrievedChunk]:
    rows = await session.execute(select(*_SOURCE_COLUMNS).where(*where).order_by(Chunk.ordinal))
    return [_to_chunk(row) for row in rows]


async def _size(session: AsyncSession, paper_id: uuid.UUID) -> tuple[int, int]:
    """(characters of chunk text, chunks that have an embedding)."""
    query = select(func.coalesce(func.sum(func.length(Chunk.text)), 0), func.count(Chunk.embedding))
    return tuple((await session.execute(query.where(Chunk.paper_id == paper_id))).one())


def source_label(paper: Paper) -> str:
    """'Devlin 2019' when the first author and year are known, otherwise the title."""
    # ponytail: M6.5 settles the authors shape (Q3); this reads {"name": ...} entries.
    first = paper.authors[0] if paper.authors else None
    name = first.get("name", "") if isinstance(first, dict) else ""
    return f"{name.split()[-1]} {paper.year}" if name and paper.year else paper.title


def format_context(paper: Paper, sources: list[RetrievedChunk]) -> str:
    label = source_label(paper)
    return "\n\n".join(
        f"[C{i}] ({', '.join(filter(None, [label, f'p.{s.page}', s.section]))})\n{s.text}"
        for i, s in enumerate(sources, start=1)
    )


async def prepare(session: AsyncSession, paper_id: uuid.UUID, question: str, embedder=None) -> Prepared:
    """Small papers go whole, in reading order; larger ones send the RETRIEVE_K nearest chunks.

    Raises NotFound, or Conflict("paper_not_ready" | "paper_not_indexed").
    """
    paper = await get_paper(session, paper_id)
    if paper.status != PaperStatus.READY:
        raise Conflict("paper_not_ready")
    chars, embedded = await _size(session, paper_id)
    whole_paper = chars <= SMALL_PAPER_CHARS
    if not whole_paper and embedded == 0:  # ingested before M4: the UI offers Re-index
        raise Conflict("paper_not_indexed")
    if whole_paper:
        sources = await _chunk_sources(session, Chunk.paper_id == paper_id)
    else:
        sources = await retrieve(session, question, paper_ids=[paper_id], k=RETRIEVE_K, embedder=embedder)
    prompt = PROMPT_TEMPLATE.format(context=format_context(paper, sources), question=question)
    return Prepared(sources=sources, system=SYSTEM_PROMPT, prompt=prompt, whole_paper=whole_paper)


def parse_citations(text: str, n: int) -> list[int]:
    """Source numbers cited in the final text: first-seen order, no repeats, unknown labels dropped."""
    cited = (int(number) for number in _CITATION.findall(text))
    return list(dict.fromkeys(i for i in cited if 1 <= i <= n))


async def save_answer(
    session: AsyncSession, paper_id: uuid.UUID, question: str, prepared: Prepared, content: str, model: str
) -> uuid.UUID:
    source_ids = [s.id for s in prepared.sources]
    output = LLMOutput(
        paper_id=paper_id,
        kind="chat",
        question=question,
        content=content,
        source_chunks=source_ids,
        cited_chunks=[source_ids[i - 1] for i in parse_citations(content, len(source_ids))],
        model=model,
        prompt_version=CHAT_PROMPT_VERSION,
        whole_paper=prepared.whole_paper,
    )
    session.add(output)
    await session.commit()
    return output.id


async def list_answers(session: AsyncSession, paper_id: uuid.UUID) -> list[Answer]:
    """Saved Q&As, oldest first, each source resolved to its chunk."""
    await get_paper(session, paper_id)
    query = select(LLMOutput).where(LLMOutput.paper_id == paper_id, LLMOutput.kind == "chat")
    outputs = list(await session.scalars(query.order_by(LLMOutput.created_at)))
    wanted = {chunk_id for output in outputs for chunk_id in output.source_chunks}
    chunks = {c.id: c for c in await _chunk_sources(session, Chunk.id.in_(wanted))}
    return [Answer(output=o, sources=[chunks.get(chunk_id) for chunk_id in o.source_chunks]) for o in outputs]
