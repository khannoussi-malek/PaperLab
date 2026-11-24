"""Saved chat answers: storing one with its sources, and reading a paper's or workspace's answers back."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat.answer_provenance import snapshot
from app.core.chat.chat import Prepared, Scope, _scope, chunk_sources
from app.core.chat.chat_context import NoteSource, _source
from app.core.chat.retrieval import RetrievedChunk
from app.core.notes.notes import _with_anchors, papers_of, parse_citations
from app.core.papers.papers import get_paper
from app.core.workspaces import workspaces
from app.models import Chunk, LLMOutput, Note


@dataclass(frozen=True)
class SavedNote:
    """A suggested note saved from an answer (D96): its block, the note, and the note's papers now, by title."""

    index: int
    note_id: uuid.UUID
    paper_ids: list[uuid.UUID]


@dataclass(frozen=True)
class SnapshotPassage:
    """A cited passage a re-ingest replaced, as the answer's snapshot kept it: its place, with no box (M33)."""

    paper_id: uuid.UUID
    page: int
    section: str | None
    from_abstract: bool


@dataclass(frozen=True)
class Answer:
    output: LLMOutput
    sources: list[RetrievedChunk | None]  # None: a re-ingest replaced that chunk
    notes: list[NoteSource | None] = field(default_factory=list)  # None: the note was deleted
    saved_notes: list[SavedNote] = field(default_factory=list)  # by block index
    replaced: list[SnapshotPassage | None] = field(
        default_factory=list
    )  # aligned with sources; None: no snapshot of it
    readings: list[LLMOutput] = field(default_factory=list)  # Ask each paper's records, in the answer's order (M8.5)


async def save_answer(
    session: AsyncSession,
    paper_id: uuid.UUID | Scope,
    question: str,
    prepared: Prepared,
    content: str,
    model: str,
    connection_name: str,
    parent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Note citations aren't stored separately: they follow from content and source_notes. The model and connection
    names are copied, so renaming or deleting the connection later never changes the answer."""
    scope = _scope(paper_id)
    source_ids = [s.id for s in prepared.sources]
    cited = parse_citations(content, len(source_ids))
    output = LLMOutput(
        paper_id=scope.paper_id,
        workspace_id=scope.workspace_id,
        kind="chat",
        question=question,
        content=content,
        source_chunks=source_ids,
        cited_chunks=[source_ids[i - 1] for i in cited],
        source_snapshot=snapshot(prepared.sources, [f"C{i}" for i in cited]),
        source_notes=[n.id for n in prepared.notes],
        notes_used=prepared.notes_used,
        notes_total=prepared.notes_total,
        model=model,
        connection_name=connection_name,
        prompt_version=prepared.prompt_version,
        whole_paper=prepared.whole_paper,
        parent_id=parent_id,
        skill_label=prepared.skill_label,
        skill_version=prepared.skill_version,
        lens=prepared.lens,
        readings=prepared.readings,
    )
    session.add(output)
    await session.commit()
    return output.id


def snapshot_passages(output: LLMOutput) -> list[SnapshotPassage | None]:
    """One per source, as sources is: the snapshot's passage for C{i+1}, or None where the answer kept none."""
    by_label = {entry["label"]: entry for entry in output.source_snapshot or []}
    found = []
    for number in range(1, len(output.source_chunks) + 1):
        entry = by_label.get(f"C{number}")
        found.append(
            None
            if entry is None
            else SnapshotPassage(uuid.UUID(entry["paper_id"]), entry["page"], entry["section"], entry["from_abstract"])
        )
    return found


async def list_answers(session: AsyncSession, paper_id: uuid.UUID | Scope) -> list[Answer]:
    """Saved Q&As, oldest first, each source resolved to its chunk and each note to how chat names it now."""
    scope = _scope(paper_id)
    if scope.workspace_id is not None:
        members = {p.id for p in await workspaces.papers(session, scope.workspace_id)}
        in_scope = LLMOutput.workspace_id == scope.workspace_id
    else:
        await get_paper(session, scope.paper_id)
        members, in_scope = {scope.paper_id}, LLMOutput.paper_id == scope.paper_id
    query = select(LLMOutput).where(in_scope, LLMOutput.kind == "chat")
    outputs = list(await session.scalars(query.order_by(LLMOutput.created_at)))
    wanted = {chunk_id for output in outputs for chunk_id in output.source_chunks}
    chunks = {c.id: c for c in await chunk_sources(session, Chunk.id.in_(wanted))}
    note_ids = {note_id for output in outputs for note_id in output.source_notes}
    notes = await _with_anchors(session, list(await session.scalars(select(Note).where(Note.id.in_(note_ids)))))
    by_id = {n.id: n for n in notes}
    saved = (
        await session.execute(
            select(Note.source_id, Note.source_block, Note.id)
            .where(Note.source_id.in_([o.id for o in outputs]), Note.source_block.is_not(None))
            .order_by(Note.source_block)
        )
    ).all()
    reading_ids = {i for o in outputs for i in o.readings}
    rows = await session.scalars(select(LLMOutput).where(LLMOutput.id.in_(reading_ids))) if reading_ids else []
    readings = {r.id: r for r in rows}
    saved_papers = await papers_of(session, [note_id for *_, note_id in saved])
    saved_notes: dict[uuid.UUID, list[SavedNote]] = {}
    for output_id, index, note_id in saved:
        saved_notes.setdefault(output_id, []).append(SavedNote(index, note_id, saved_papers.get(note_id, [])))
    return [
        Answer(
            output=o,
            sources=[chunks.get(chunk_id) for chunk_id in o.source_chunks],
            replaced=snapshot_passages(o),
            # None: the note was deleted, or is no longer linked to a paper in scope (spec §4.3).
            notes=[None if note_id not in by_id else _source(by_id[note_id], members) for note_id in o.source_notes],
            saved_notes=saved_notes.get(o.id, []),
            readings=[readings[i] for i in o.readings if i in readings],
        )
        for o in outputs
    ]
