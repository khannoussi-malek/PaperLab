"""AI briefs (M16 L7, D50): a model's summary of one lens of one paper, saved as an llm_outputs row (kind 'brief').

A brief is stale when the chunks it was written from differ from the chunks it would be written from now. One
comparison covers a role fix and a re-ingest, with nothing to keep in sync. Briefs never count toward a reading pass
(D118): they are AI text, labelled as such.
"""

import re
import uuid
from dataclasses import dataclass
from itertools import accumulate

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import lenses, prompts
from app.core.chat import SMALL_PAPER_CHARS, Prepared, chunk_sources, format_context, parse_citations
from app.core.errors import Conflict, InvalidInput
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, LLMOutput, PaperStatus

OUTPUT_KIND = "brief"  # the llm_outputs.kind of a brief, as claims.py and evidence_cards.py name theirs
BRIEF_PROMPT_VERSION = 1
BRIEFABLE = ("key_ideas", "critical", "method", "related")  # every lens but Full paper


def _load(version: int) -> tuple[str, str, dict[str, str]]:
    """The system prompt, the template and one instruction per lens, split on `<!-- name -->` lines."""
    system, *named = re.split(r"\n<!-- (\w+) -->\n", prompts.load("brief", version).strip())
    parts = {name: part.strip() for name, part in zip(named[::2], named[1::2])}
    template = parts.pop("prompt")
    if sorted(parts) != sorted(BRIEFABLE):
        raise RuntimeError(f"brief.v{version}.md needs one instruction for each of {', '.join(BRIEFABLE)}")
    return system.strip(), template, parts


SYSTEM_PROMPT, PROMPT_TEMPLATE, LENS_INSTRUCTIONS = _load(BRIEF_PROMPT_VERSION)


@dataclass(frozen=True)
class Brief:
    output: LLMOutput
    sources: list[RetrievedChunk | None]  # None: a re-ingest replaced that chunk
    stale: bool


def cut_to_budget(sources: list[RetrievedChunk], budget: int = SMALL_PAPER_CHARS) -> list[RetrievedChunk]:
    """The longest start of `sources`, in their order, whose text fits `budget` characters. A chunk is never split,
    and the first one is always kept, so a brief never reads nothing."""
    totals = accumulate(len(source.text) for source in sources)
    return [source for source, total in zip(sources, totals) if total <= budget] or sources[:1]


async def _lens_sources(session: AsyncSession, paper_id: uuid.UUID, lens: str) -> list[RetrievedChunk]:
    found = await lenses.lens_chunks(session, paper_id, lens)
    return await chunk_sources(session, Chunk.id.in_(found.chunk_ids))


async def prepare_brief(session: AsyncSession, paper_id: uuid.UUID, lens: str) -> Prepared:
    """The lens's chunks in reading order, cut to SMALL_PAPER_CHARS without splitting one (whole_paper=False when cut).

    Raises InvalidInput("lens_not_briefable") for Full paper or an unknown lens, NotFound, or Conflict
    ("needs_full_text" | "paper_not_ready" | "lens_empty")."""
    if lens not in BRIEFABLE:
        raise InvalidInput("lens_not_briefable")
    paper = await get_paper(session, paper_id)
    if not paper.has_pdf:
        raise Conflict("needs_full_text")  # R1: no PDF, no sections, so no lens to brief; said before lens_empty
    if paper.status != PaperStatus.READY:
        raise Conflict("paper_not_ready")
    every = await _lens_sources(session, paper_id, lens)
    if not every:
        raise Conflict("lens_empty")
    sources = cut_to_budget(every)
    prompt = PROMPT_TEMPLATE.format(lens_instruction=LENS_INSTRUCTIONS[lens], context=format_context(paper, sources))
    return Prepared(
        sources=sources,
        system=SYSTEM_PROMPT,
        prompt=prompt,
        whole_paper=len(sources) == len(every),
        prompt_version=BRIEF_PROMPT_VERSION,
    )


async def save_brief(
    session: AsyncSession,
    paper_id: uuid.UUID,
    lens: str,
    prepared: Prepared,
    content: str,
    model: str,
    connection_name: str,
) -> uuid.UUID:
    """The model and connection names are copied, as chat's are, so renaming the connection never changes a brief."""
    source_ids = [s.id for s in prepared.sources]
    output = LLMOutput(
        paper_id=paper_id,
        kind=OUTPUT_KIND,
        lens=lens,
        content=content,
        source_chunks=source_ids,
        cited_chunks=[source_ids[i - 1] for i in parse_citations(content, len(source_ids))],
        whole_paper=prepared.whole_paper,
        model=model,
        connection_name=connection_name,
        prompt_version=prepared.prompt_version,
    )
    session.add(output)
    await session.commit()
    return output.id


async def list_briefs(session: AsyncSession, paper_id: uuid.UUID) -> list[Brief]:
    """The newest brief per lens, in BRIEFABLE order, with its sources resolved and whether it is stale. Both sides
    of the stale test go through the same budget cut, so a partial brief isn't stale for being cut. Raises NotFound."""
    await get_paper(session, paper_id)
    query = select(LLMOutput).where(LLMOutput.paper_id == paper_id, LLMOutput.kind == OUTPUT_KIND)
    newest: dict[str, LLMOutput] = {}
    for output in await session.scalars(query.order_by(LLMOutput.created_at.desc(), LLMOutput.id.desc())):
        newest.setdefault(output.lens, output)
    wanted = {chunk_id for output in newest.values() for chunk_id in output.source_chunks}
    chunks = {c.id: c for c in await chunk_sources(session, Chunk.id.in_(wanted))}
    found = []
    # ponytail: re-reads the sections once per briefed lens (at most 4); one paper_lenses read if it shows up
    for lens in (lens for lens in BRIEFABLE if lens in newest):
        output = newest[lens]
        now = {source.id for source in cut_to_budget(await _lens_sources(session, paper_id, lens))}
        found.append(Brief(output, [chunks.get(i) for i in output.source_chunks], set(output.source_chunks) != now))
    return found
