"""M33: the passages an answer cited, copied when it is saved (llm_outputs.source_snapshot).

A re-ingest replaces every chunk with a new one, so an answer's [C#] would point at nothing. The copy keeps each cited
passage's paper, page, section and text, so the citation still opens the right page, and the view can tell whether
the text is still in the paper.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.notes import MCP_OUTPUT_KIND
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, LLMOutput, Note, Paper, Provenance

CURRENT, CHANGED, NOT_RECORDED = "current", "changed", "not_recorded"
MAX_SNAPSHOT_PASSAGES = 30
MAX_SNAPSHOT_CHARS = 2_000


def snapshot(chunks: list[RetrievedChunk], cited_labels: list[str]) -> list[dict]:
    """One entry per cited label, in label order: the first MAX_SNAPSHOT_PASSAGES of them, each text cut at
    MAX_SNAPSHOT_CHARS. `chunks[i]` is the passage labelled C{i+1}; a label outside `chunks` is skipped.
    """
    numbers = sorted({int(label[1:]) for label in cited_labels})
    entries = []
    for number in numbers:
        if not 1 <= number <= len(chunks) or len(entries) == MAX_SNAPSHOT_PASSAGES:
            continue
        chunk = chunks[number - 1]
        entries.append(
            {
                "label": f"C{number}",
                "paper_id": str(chunk.paper_id),
                "page": chunk.page,
                "section": chunk.section,
                "text": chunk.text[:MAX_SNAPSHOT_CHARS],
                "from_abstract": chunk.from_abstract,
            }
        )
    return entries


@dataclass(frozen=True)
class AnswerPassage:
    label: str  # "C3": the marker the answer cites
    paper_id: uuid.UUID | None  # None: not recorded, and its chunk is gone
    paper_title: str | None
    page: int | None
    section: str | None
    text: str | None  # None: not recorded
    state: str  # CURRENT, CHANGED or NOT_RECORDED


@dataclass(frozen=True)
class AnswerProvenance:
    model: str
    connection_name: str | None
    prompt_version: int
    skill_label: str | None
    created_at: datetime
    passages: list[AnswerPassage]
    out_of_date: bool  # a cited passage has changed since the answer was written


@dataclass(frozen=True)
class McpNote:
    """A note an MCP client added: nothing about how it was made is known, so there is nothing to show but that."""


def _squash(text: str) -> str:
    return " ".join(text.split())


async def _paper_texts(session: AsyncSession, paper_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each paper's current chunks, whitespace-squashed and joined in reading order: what a snapshot must appear in."""
    rows = await session.execute(
        select(Chunk.paper_id, Chunk.text).where(Chunk.paper_id.in_(paper_ids)).order_by(Chunk.paper_id, Chunk.ordinal)
    )
    parts: dict[uuid.UUID, list[str]] = {}
    for paper_id, text in rows:
        parts.setdefault(paper_id, []).append(text)
    return {paper_id: _squash(" ".join(texts)) for paper_id, texts in parts.items()}


async def _live_chunks(session: AsyncSession, chunk_ids: list[uuid.UUID]) -> dict[uuid.UUID, Chunk]:
    rows = await session.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    return {chunk.id: chunk for chunk in rows}


def _label_numbers(output: LLMOutput) -> list[int]:
    """The C numbers an answer cites: from its snapshot, and from the chunks it cited, which a snapshot cap may cut."""
    numbers = {int(entry["label"][1:]) for entry in output.source_snapshot or []}
    position = {chunk_id: n for n, chunk_id in enumerate(output.source_chunks, start=1)}
    numbers |= {position[chunk_id] for chunk_id in output.cited_chunks if chunk_id in position}
    return sorted(numbers)


async def provenance(session: AsyncSession, output_id: uuid.UUID) -> AnswerProvenance:
    """How an answer was made, and where each cited passage stands now. Raises NotFound("answer_not_found")."""
    output = await session.get(LLMOutput, output_id)
    if output is None:
        raise NotFound("answer_not_found")
    snapshot_by_label = {entry["label"]: entry for entry in output.source_snapshot or []}
    numbers = _label_numbers(output)
    chunk_ids = [output.source_chunks[n - 1] for n in numbers if n <= len(output.source_chunks)]
    live = await _live_chunks(session, chunk_ids)
    paper_ids = {uuid.UUID(entry["paper_id"]) for entry in snapshot_by_label.values()} | {
        c.paper_id for c in live.values()
    }
    texts = await _paper_texts(session, paper_ids)
    rows = await session.execute(select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids)))
    titles = {paper_id: title for paper_id, title in rows}
    passages = [
        _passage(
            f"C{n}",
            output,
            live.get(output.source_chunks[n - 1]) if n <= len(output.source_chunks) else None,
            snapshot_by_label.get(f"C{n}"),
            texts,
            titles,
        )
        for n in numbers
    ]
    return AnswerProvenance(
        model=output.model,
        connection_name=output.connection_name,
        prompt_version=output.prompt_version,
        skill_label=output.skill_label,
        created_at=output.created_at,
        passages=passages,
        out_of_date=any(p.state == CHANGED for p in passages),
    )


def _passage(label, output, chunk, entry, texts, titles) -> AnswerPassage:
    if entry is not None:
        # The snapshot's text is in the paper when its squashed form is in the paper's squashed chunk text.
        paper_id = uuid.UUID(entry["paper_id"])
        state = CURRENT if _squash(entry["text"]) in texts.get(paper_id, "") else CHANGED
        if chunk is not None:
            return AnswerPassage(
                label, paper_id, titles.get(paper_id), chunk.page, chunk.section_title, chunk.text, state
            )
        return AnswerPassage(
            label, paper_id, titles.get(paper_id), entry["page"], entry["section"], entry["text"], state
        )
    if chunk is not None and output.source_snapshot is None:  # saved before M33: the live passage is all there is
        return AnswerPassage(
            label, chunk.paper_id, titles.get(chunk.paper_id), chunk.page, chunk.section_title, chunk.text, CURRENT
        )
    # Not in the snapshot (past its cap, or saved before M33 and gone): nothing recorded to compare with.
    if chunk is None:
        return AnswerPassage(label, None, None, None, None, None, NOT_RECORDED)
    return AnswerPassage(
        label, chunk.paper_id, titles.get(chunk.paper_id), chunk.page, chunk.section_title, None, NOT_RECORDED
    )


async def note_provenance(session: AsyncSession, note_id: uuid.UUID) -> AnswerProvenance | McpNote:
    """The provenance of the answer an AI note came from, or McpNote. Raises NotFound("note_not_found" | "not_ai" for
    a note a person wrote | "answer_not_found")."""
    note = await session.get(Note, note_id)
    if note is None:
        raise NotFound("note_not_found")
    if note.provenance == Provenance.HUMAN or note.source_id is None:
        raise NotFound("not_ai")
    output = await session.get(LLMOutput, note.source_id)
    if output is None:
        raise NotFound("answer_not_found")
    if output.kind == MCP_OUTPUT_KIND:
        return McpNote()
    return await provenance(session, output.id)
