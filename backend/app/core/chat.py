"""Chat over one paper or one workspace: choose the sources, build the prompt, store answers.

Never writes notes: an answer becomes a note only through notes.promote_llm_fragment.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import prompts, workspaces
from app.core.errors import Conflict
from app.core.notes import Anchor, NoteView, _with_anchors
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk, _to_chunk, retrieve
from app.models import Chunk, LLMOutput, Note, Paper, PaperStatus, Provenance

CHAT_PROMPT_VERSION = 1
WORKSPACE_PROMPT_VERSION = 1
# Each file holds the system prompt, then the user prompt template after the marker line.
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat", CHAT_PROMPT_VERSION).split("\n<!-- prompt -->\n")
WORKSPACE_SYSTEM_PROMPT, WORKSPACE_PROMPT_TEMPLATE = prompts.load("chat_workspace", WORKSPACE_PROMPT_VERSION).split(
    "\n<!-- prompt -->\n"
)
# ponytail: characters stand in for tokens. Revisit with the eval numbers or a model's real context size.
SMALL_PAPER_CHARS = 24_000
RETRIEVE_K = 8
# Workspace notes. With OLLAMA_NUM_CTX = 16_384: ~0.5k tokens of instructions, ~3k for 8 passages, ~4k for
# notes, leaving ~2k for the answer.
NOTE_QUOTE_CHARS = 160
NOTE_BODY_CHARS = 400
# ponytail: newest-first is a guess at relevance; rank by similarity to the question if users hit the budget.
NOTES_CHAR_BUDGET = 16_000
BADGES = {Provenance.HUMAN: "You", Provenance.LLM: "AI", Provenance.LLM_EDITED: "AI · edited"}
_CITATION = re.compile(r"\[([CN])(\d+)\]")
_SOURCE_COLUMNS = (Chunk.id, Chunk.paper_id, Chunk.page, Chunk.section_title, Chunk.bbox, Chunk.text)


@dataclass(frozen=True)
class Scope:
    """What a chat is about: one paper or one workspace. Functions also take a bare paper id."""

    paper_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None

    def __post_init__(self):
        if (self.paper_id is None) == (self.workspace_id is None):
            raise ValueError("Scope needs exactly one of paper_id or workspace_id")


def _scope(scope: uuid.UUID | Scope) -> Scope:
    return scope if isinstance(scope, Scope) else Scope(paper_id=scope)


@dataclass(frozen=True)
class NoteSource:
    id: uuid.UUID
    paper_id: uuid.UUID  # the anchor the notes block quoted
    page: int
    provenance: str


@dataclass(frozen=True)
class Prepared:
    sources: list[RetrievedChunk]  # C{i} is sources[i-1]
    system: str
    prompt: str
    whole_paper: bool
    prompt_version: int = CHAT_PROMPT_VERSION
    notes: list[NoteSource] = field(default_factory=list)  # N{i} is notes[i-1]; workspace chat only
    notes_total: int | None = None  # every note in the workspace; None outside workspace chat

    @property
    def notes_used(self) -> int | None:
        return None if self.notes_total is None else len(self.notes)


@dataclass(frozen=True)
class Answer:
    output: LLMOutput
    sources: list[RetrievedChunk | None]  # None: a re-ingest replaced that chunk
    notes: list[NoteSource | None] = field(default_factory=list)  # None: the note was deleted


async def _chunk_sources(session: AsyncSession, *where) -> list[RetrievedChunk]:
    rows = await session.execute(select(*_SOURCE_COLUMNS).where(*where).order_by(Chunk.ordinal))
    return [_to_chunk(row) for row in rows]


async def _size(session: AsyncSession, paper_id: uuid.UUID) -> tuple[int, int]:
    """(characters of chunk text, chunks that have an embedding)."""
    query = select(func.coalesce(func.sum(func.length(Chunk.text)), 0), func.count(Chunk.embedding))
    return tuple((await session.execute(query.where(Chunk.paper_id == paper_id))).one())


def source_label(paper: Paper) -> str:
    """'Devlin 2019', or 'Devlin' without a year. The title when no author name is known."""
    # ponytail: the last word of the first non-blank name. "Le Cun" gives "Cun"; the label only orients the model.
    family = next((name.split()[-1] for name in paper.authors if name.strip()), None)
    if family is None:
        return paper.title
    return f"{family} {paper.year}" if paper.year else family


def format_context(paper: Paper | dict[uuid.UUID, Paper], sources: list[RetrievedChunk]) -> str:
    """One Paper labels every source; a paper_id → Paper map labels each source with its own paper."""

    def label(source: RetrievedChunk) -> str:
        return source_label(paper if isinstance(paper, Paper) else paper[source.paper_id])

    return "\n\n".join(
        f"[C{i}] ({', '.join(filter(None, [label(s), f'p.{s.page}', s.section]))})\n{s.text}"
        for i, s in enumerate(sources, start=1)
    )


def _cut(text: str, limit: int) -> str:
    """Whitespace collapsed, then at most `limit` characters; a cut text ends with …."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _first_anchor(note: NoteView, paper_ids) -> Anchor | None:
    """The note's first anchor in reading order, preferring anchors on the given papers."""
    anchors = [a for a in note.anchors if a.paper_id in paper_ids] or note.anchors
    return min(anchors, key=lambda a: (a.page, min(r[1] for r in a.bbox), str(a.paper_id)), default=None)


def format_notes_block(notes: list[NoteView], papers: dict[uuid.UUID, Paper]) -> tuple[str, list[NoteSource]]:
    """One [N{i}] line per note, newest first, while the block fits NOTES_CHAR_BUDGET. A line is never split.

    Returns the block and the notes it holds (N{i} is the i-th); every note must be anchored on one of `papers`.
    """
    lines: list[str] = []
    used: list[NoteSource] = []
    for note in sorted(notes, key=lambda n: n.updated_at, reverse=True):
        anchor = _first_anchor(note, papers)
        label = f"{BADGES[note.provenance]} · {source_label(papers[anchor.paper_id])} p.{anchor.page}"
        line = f'[N{len(lines) + 1}] ({label}) "{_cut(anchor.quoted_text, NOTE_QUOTE_CHARS)}"'
        if body := _cut(note.body, NOTE_BODY_CHARS):
            line += f" — {body}"
        if sum(map(len, lines)) + len(lines) + len(line) > NOTES_CHAR_BUDGET:  # len(lines): the newlines
            break
        lines.append(line)
        used.append(NoteSource(id=note.id, paper_id=anchor.paper_id, page=anchor.page, provenance=note.provenance))
    return "\n".join(lines), used


async def _prepare_workspace(session: AsyncSession, workspace_id: uuid.UUID, question: str, embedder) -> Prepared:
    """Retrieved passages across the workspace's papers plus all its notes, trimmed. No whole-paper skip.

    Raises NotFound, or Conflict("workspace_empty" | "workspace_not_indexed").
    """
    members = {p.id: p for p in await workspaces.papers(session, workspace_id)}
    if not members:
        raise Conflict("workspace_empty")
    ready = [paper_id for paper_id, paper in members.items() if paper.status == PaperStatus.READY]
    if not await session.scalar(select(func.count(Chunk.embedding)).where(Chunk.paper_id.in_(ready))):
        raise Conflict("workspace_not_indexed")
    sources = await retrieve(session, question, paper_ids=ready, k=RETRIEVE_K, embedder=embedder)
    every_note = await workspaces.notes(session, workspace_id)
    block, used = format_notes_block(every_note, members)
    prompt = WORKSPACE_PROMPT_TEMPLATE.format(
        context=format_context(members, sources), notes=block or "(none)", question=question
    )
    return Prepared(
        sources=sources,
        system=WORKSPACE_SYSTEM_PROMPT,
        prompt=prompt,
        whole_paper=False,
        prompt_version=WORKSPACE_PROMPT_VERSION,
        notes=used,
        notes_total=len(every_note),
    )


async def prepare(session: AsyncSession, paper_id: uuid.UUID | Scope, question: str, embedder=None) -> Prepared:
    """A workspace scope goes to _prepare_workspace. For a paper: small papers go whole, in reading order;
    larger ones send the RETRIEVE_K nearest chunks.

    Raises NotFound, or Conflict("paper_not_ready" | "paper_not_indexed").
    """
    scope = _scope(paper_id)
    if scope.workspace_id is not None:
        return await _prepare_workspace(session, scope.workspace_id, question, embedder)
    paper_id = scope.paper_id
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


def parse_citations(text: str, n: int, kind: str = "C") -> list[int]:
    """[C{i}] (or [N{i}]) numbers cited in the final text: first-seen order, no repeats, unknown labels dropped."""
    cited = (int(number) for label, number in _CITATION.findall(text) if label == kind)
    return list(dict.fromkeys(i for i in cited if 1 <= i <= n))


async def save_answer(
    session: AsyncSession, paper_id: uuid.UUID | Scope, question: str, prepared: Prepared, content: str, model: str
) -> uuid.UUID:
    """Note citations aren't stored separately: they follow from content and source_notes."""
    scope = _scope(paper_id)
    source_ids = [s.id for s in prepared.sources]
    output = LLMOutput(
        paper_id=scope.paper_id,
        workspace_id=scope.workspace_id,
        kind="chat",
        question=question,
        content=content,
        source_chunks=source_ids,
        cited_chunks=[source_ids[i - 1] for i in parse_citations(content, len(source_ids))],
        source_notes=[n.id for n in prepared.notes],
        notes_used=prepared.notes_used,
        notes_total=prepared.notes_total,
        model=model,
        prompt_version=prepared.prompt_version,
        whole_paper=prepared.whole_paper,
    )
    session.add(output)
    await session.commit()
    return output.id


def _note_source(note: NoteView | None, paper_ids) -> NoteSource | None:
    anchor = _first_anchor(note, paper_ids) if note is not None else None
    if anchor is None:  # the note was deleted, or its paper was
        return None
    return NoteSource(id=note.id, paper_id=anchor.paper_id, page=anchor.page, provenance=note.provenance)


async def list_answers(session: AsyncSession, paper_id: uuid.UUID | Scope) -> list[Answer]:
    """Saved Q&As, oldest first, each source resolved to its chunk and each note to its current anchor."""
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
    chunks = {c.id: c for c in await _chunk_sources(session, Chunk.id.in_(wanted))}
    note_ids = {note_id for output in outputs for note_id in output.source_notes}
    notes = await _with_anchors(session, list(await session.scalars(select(Note).where(Note.id.in_(note_ids)))))
    by_id = {n.id: n for n in notes}
    return [
        Answer(
            output=o,
            sources=[chunks.get(chunk_id) for chunk_id in o.source_chunks],
            notes=[_note_source(by_id.get(note_id), members) for note_id in o.source_notes],
        )
        for o in outputs
    ]
