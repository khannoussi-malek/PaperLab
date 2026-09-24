"""Chat over one paper or one workspace: choose the sources, build the prompt, store answers.

Never writes notes: an answer becomes a note only through notes.promote_llm_fragment.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import embedding_index, prompts, workspaces
from app.core.errors import Conflict, NotFound
from app.core.notes import Anchor, NoteView, _with_anchors, list_notes_for_paper
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk, _to_chunk, query_embedder, retrieve
from app.models import Chunk, LLMOutput, Note, Paper, PaperStatus, Provenance

CHAT_PROMPT_VERSION = 2  # v2: the paper's notes follow its passages; a follow-up adds the earlier questions
WORKSPACE_PROMPT_VERSION = 1
# Each file holds the system prompt, then the user prompt template after the marker line.
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat", CHAT_PROMPT_VERSION).split("\n<!-- prompt -->\n")
WORKSPACE_SYSTEM_PROMPT, WORKSPACE_PROMPT_TEMPLATE = prompts.load("chat_workspace", WORKSPACE_PROMPT_VERSION).split(
    "\n<!-- prompt -->\n"
)
# ponytail: characters stand in for tokens. Revisit with the eval numbers or a model's real context size.
SMALL_PAPER_CHARS = 24_000
RETRIEVE_K = 8
# A follow-up's earlier passages plus fresh ones: ~4.5k tokens, so with notes it still fits OLLAMA_NUM_CTX.
FOLLOW_UP_SOURCES = 12
# A follow-up carries its parent answer's question and passages, and those of at most four answers before it.
MAX_THREAD_ANSWERS = 5
# Notes, in both chats. With OLLAMA_NUM_CTX = 16_384: ~0.5k tokens of instructions, ~3k for 8 passages, ~4k for
# notes, about 7.5k of the 16k context, leaving ~9k for the answer. A whole small paper (~6k) still leaves ~5.5k.
NOTE_QUOTE_CHARS = 160
NOTE_BODY_CHARS = 400
# ponytail: newest-first is a guess at relevance; rank by similarity to the question if users hit the budget.
NOTES_CHAR_BUDGET = 16_000
# A bare "(none)" here once got parroted back as an answer's entire content by a small local model asked a
# question that itself mentioned "notes" — a short, quotable placeholder sitting right above "Question: ..." reads
# too much like a plausible answer to a weak model. A full sentence doesn't.
NO_NOTES_PLACEHOLDER = "No notes have been written yet."
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
    notes: list[NoteSource] = field(default_factory=list)  # N{i} is notes[i-1]
    notes_total: int | None = None  # every note in the paper or workspace

    @property
    def notes_used(self) -> int | None:
        return None if self.notes_total is None else len(self.notes)


@dataclass(frozen=True)
class Thread:
    """What a follow-up carries from the questions before it, oldest first: the questions and their passages.

    Never their answers: the model reads the paper's evidence again instead of building on its own earlier text.
    """

    questions: list[str]
    source_ids: list[uuid.UUID]  # most relevant first: past FOLLOW_UP_SOURCES, the last ones are dropped


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


async def papers_needing_search(session: AsyncSession) -> int:
    """Ready papers too long to send whole, so chat on them retrieves: what the library's notice counts while no search
    model is downloaded (P1)."""
    long = (
        select(Chunk.paper_id)
        .join(Paper, Paper.id == Chunk.paper_id)
        .where(Paper.status == PaperStatus.READY)
        .group_by(Chunk.paper_id)
        .having(func.sum(func.length(Chunk.text)) > SMALL_PAPER_CHARS)
    )
    return await session.scalar(select(func.count()).select_from(long.subquery()))


def follow_up_sources(
    earlier: list[RetrievedChunk], fresh: list[RetrievedChunk], limit: int = FOLLOW_UP_SOURCES
) -> list[RetrievedChunk]:
    """Earlier passages first, then fresh ones, each once. Every fresh passage stays; earlier passages that aren't
    also fresh fill what's left of `limit` in their given order, best first."""
    unique = list({chunk.id: chunk for chunk in earlier}.values())  # a dict keeps each passage's first position
    earlier_ids, fresh_ids = {chunk.id for chunk in unique}, {chunk.id for chunk in fresh}
    fresh_only = [chunk for chunk in fresh if chunk.id not in earlier_ids]
    room = limit - len(fresh_only) - len(earlier_ids & fresh_ids)
    earlier_only = [chunk for chunk in unique if chunk.id not in fresh_ids][: max(room, 0)]
    kept = fresh_ids | {chunk.id for chunk in earlier_only}
    return [chunk for chunk in unique if chunk.id in kept] + fresh_only


async def load_thread(session: AsyncSession, paper_id: uuid.UUID, parent_id: uuid.UUID) -> Thread:
    """What a follow-up to `parent_id` carries: that answer and up to MAX_THREAD_ANSWERS - 1 before it, on `paper_id`.

    Raises NotFound (an unknown paper, or "parent_not_found"), or Conflict("parent_scope") when the answer belongs
    to another paper or a workspace.
    """
    await get_paper(session, paper_id)
    parent = await session.get(LLMOutput, parent_id)
    if parent is None or parent.kind != "chat":
        raise NotFound("parent_not_found")
    if parent.paper_id != paper_id:
        raise Conflict("parent_scope")
    # A parent_id is only ever saved on the same paper's answers, and the FK nulls it when that answer is deleted.
    chain = [parent]
    while chain[-1].parent_id is not None and len(chain) < MAX_THREAD_ANSWERS:
        chain.append(await session.get(LLMOutput, chain[-1].parent_id))
    # A follow-up saves the passages it carried ahead of the ones it found, so each answer's own finds come first,
    # newest answer first: otherwise a long thread keeps carrying its first question's passages and drops the last.
    own = [
        [chunk_id for chunk_id in output.source_chunks if older is None or chunk_id not in older.source_chunks]
        for output, older in zip(chain, [*chain[1:], None])
    ]
    source_ids = [*(chunk_id for ids in own for chunk_id in ids), *(i for o in chain for i in o.source_chunks)]
    return Thread(
        questions=[output.question for output in reversed(chain)], source_ids=list(dict.fromkeys(source_ids))
    )


async def _earlier_sources(session: AsyncSession, thread: Thread, paper_id: uuid.UUID) -> list[RetrievedChunk]:
    """The thread's passages still on this paper, in thread order; a re-ingest may have replaced some."""
    where = (Chunk.id.in_(thread.source_ids), Chunk.paper_id == paper_id)
    found = {chunk.id: chunk for chunk in await _chunk_sources(session, *where)}
    return [found[i] for i in dict.fromkeys(thread.source_ids) if i in found]


def _earlier_block(thread: Thread | None) -> str:
    if thread is None or not thread.questions:
        return ""
    questions = "".join(f"- {question}\n" for question in thread.questions)
    return f"Earlier questions in this conversation, oldest first:\n{questions}\n"


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
        # A promoted AI note's body/quote is a verbatim answer slice and may still carry that answer's own
        # [C#]/[N#] markers; strip them first so the model can't echo one that now points elsewhere.
        quote = _cut(_CITATION.sub("", anchor.quoted_text), NOTE_QUOTE_CHARS)
        line = f'[N{len(lines) + 1}] ({label}) "{quote}"'
        if body := _cut(_CITATION.sub("", note.body), NOTE_BODY_CHARS):
            line += f" — {body}"
        if sum(map(len, lines)) + len(lines) + len(line) > NOTES_CHAR_BUDGET:  # len(lines): the newlines
            break
        lines.append(line)
        used.append(NoteSource(id=note.id, paper_id=anchor.paper_id, page=anchor.page, provenance=note.provenance))
    return "\n".join(lines), used


async def _prepare_workspace(session: AsyncSession, workspace_id: uuid.UUID, question: str, embedder) -> Prepared:
    """Retrieved passages across the workspace's papers plus all its notes, trimmed. No whole-paper skip.

    Raises NotFound, or Conflict("workspace_empty" | "search_not_set_up" | "workspace_not_indexed" |
    "embedding_model_changed").
    """
    members = {p.id: p for p in await workspaces.papers(session, workspace_id)}
    if not members:
        raise Conflict("workspace_empty")
    embedder = await query_embedder(embedder)  # before the index: with no model, no paper has vectors (D136)
    ready = [paper_id for paper_id, paper in members.items() if paper.status == PaperStatus.READY]
    if not await session.scalar(select(func.count(Chunk.embedding)).where(Chunk.paper_id.in_(ready))):
        raise Conflict("workspace_not_indexed")
    await embedding_index.check_model(session, settings.embed_model, ready)
    sources = await retrieve(session, question, paper_ids=ready, k=RETRIEVE_K, embedder=embedder)
    every_note = await workspaces.notes(session, workspace_id)
    block, used = format_notes_block(every_note, members)
    prompt = WORKSPACE_PROMPT_TEMPLATE.format(
        context=format_context(members, sources), notes=block or NO_NOTES_PLACEHOLDER, question=question
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


async def prepare(
    session: AsyncSession, paper_id: uuid.UUID | Scope, question: str, embedder=None, thread: Thread | None = None
) -> Prepared:
    """A workspace scope goes to _prepare_workspace. For a paper: small papers go whole, in reading order;
    larger ones send the RETRIEVE_K nearest chunks. The paper's notes follow, newest first, as in workspace chat.
    A follow-up (`thread`) adds the earlier questions, and a large paper's earlier passages ahead of the fresh ones.

    Raises NotFound, or Conflict("paper_not_ready" | "search_not_set_up" | "paper_not_indexed" |
    "embedding_model_changed"). A small paper needs no search model.
    """
    scope = _scope(paper_id)
    if scope.workspace_id is not None:
        if thread is not None:
            # ponytail: follow-ups are measured on paper chat first; workspace chat gets them if they earn their keep.
            raise ValueError("follow-ups are paper chat only for now")
        return await _prepare_workspace(session, scope.workspace_id, question, embedder)
    paper_id = scope.paper_id
    paper = await get_paper(session, paper_id)
    if paper.status != PaperStatus.READY:
        raise Conflict("paper_not_ready")
    chars, embedded = await _size(session, paper_id)
    whole_paper = chars <= SMALL_PAPER_CHARS
    if not whole_paper:
        embedder = await query_embedder(embedder)  # before the index: with no model, no paper has vectors (D136)
        if embedded == 0:  # ingested before M4, or before the model arrived: the UI offers Re-index
            raise Conflict("paper_not_indexed")
    if whole_paper:
        sources = await _chunk_sources(session, Chunk.paper_id == paper_id)
    else:
        await embedding_index.check_model(session, settings.embed_model, [paper_id])
        sources = await retrieve(session, question, paper_ids=[paper_id], k=RETRIEVE_K, embedder=embedder)
        if thread is not None:
            sources = follow_up_sources(await _earlier_sources(session, thread, paper_id), sources)
    every_note = await list_notes_for_paper(session, paper_id)
    block, used = format_notes_block(every_note, {paper_id: paper})
    context = format_context(paper, sources)
    earlier = _earlier_block(thread)
    prompt = PROMPT_TEMPLATE.format(context=context, notes=block or NO_NOTES_PLACEHOLDER, earlier=earlier, question=question)
    return Prepared(
        sources=sources, system=SYSTEM_PROMPT, prompt=prompt, whole_paper=whole_paper, notes=used,
        notes_total=len(every_note),
    )


def parse_citations(text: str, n: int, kind: str = "C") -> list[int]:
    """[C{i}] (or [N{i}]) numbers cited in the final text: first-seen order, no repeats, unknown labels dropped."""
    cited = (int(number) for label, number in _CITATION.findall(text) if label == kind)
    return list(dict.fromkeys(i for i in cited if 1 <= i <= n))


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
        connection_name=connection_name,
        prompt_version=prepared.prompt_version,
        whole_paper=prepared.whole_paper,
        parent_id=parent_id,
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
