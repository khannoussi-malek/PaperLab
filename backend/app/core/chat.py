"""Chat over one paper or one workspace: choose the sources, build the prompt, store answers.

Never writes notes: an answer becomes a note through notes.promote_llm_fragment or notes.save_suggestion, both a
click by the reader.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import prompts, workspaces
from app.core.errors import Conflict, NotFound
from app.core.notes import _CITATION, Anchor, NoteView, _with_anchors, list_notes_for_paper, papers_of, parse_citations
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk, _to_chunk, retrieve, searchable
from app.models import Chunk, LLMOutput, Note, Paper, PaperStatus, Provenance

# v5: the note-block delimiter has a literal example, after the answer eval found qwen3:8b using near-miss markers
# (<::note>, -::note); v4: asked for notes, the model writes each as a :::note block (M20); v3: [N#] is explicitly
# citation-only, so "generate notes" can't get mislabeled as one.
CHAT_PROMPT_VERSION = 5
WORKSPACE_PROMPT_VERSION = 4  # v4: the same sharpened :::note example
# Each file holds the system prompt, then the user prompt template after this marker line.
PROMPT_MARKER = "\n<!-- prompt -->\n"
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat", CHAT_PROMPT_VERSION).split(PROMPT_MARKER)
WORKSPACE_SYSTEM_PROMPT, WORKSPACE_PROMPT_TEMPLATE = prompts.load("chat_workspace", WORKSPACE_PROMPT_VERSION).split(
    PROMPT_MARKER
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
    paper_id: uuid.UUID  # the paper the notes block named it by
    page: int | None  # its first passage there; None for a note on the whole paper
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
class SavedNote:
    """A suggested note saved from an answer (D96): its block, the note, and the note's papers now, by title."""

    index: int
    note_id: uuid.UUID
    paper_ids: list[uuid.UUID]


@dataclass(frozen=True)
class Answer:
    output: LLMOutput
    sources: list[RetrievedChunk | None]  # None: a re-ingest replaced that chunk
    notes: list[NoteSource | None] = field(default_factory=list)  # None: the note was deleted
    saved_notes: list[SavedNote] = field(default_factory=list)  # by block index


async def chunk_sources(session: AsyncSession, *where) -> list[RetrievedChunk]:
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
    return Thread(questions=[output.question for output in reversed(chain)], source_ids=list(dict.fromkeys(source_ids)))


async def _earlier_sources(session: AsyncSession, thread: Thread, paper_id: uuid.UUID) -> list[RetrievedChunk]:
    """The thread's passages still on this paper, in thread order; a re-ingest may have replaced some."""
    where = (Chunk.id.in_(thread.source_ids), Chunk.paper_id == paper_id)
    found = {chunk.id: chunk for chunk in await chunk_sources(session, *where)}
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
    """The note's first passage on these papers in reading order; None when it has none there."""
    anchors = [a for a in note.anchors if a.paper_id in paper_ids]
    return min(anchors, key=lambda a: (a.page, min(r[1] for r in a.bbox), str(a.paper_id)), default=None)


def _source(note: NoteView, paper_ids) -> NoteSource | None:
    """The note as chat names it: by its first passage on these papers; else by its first linked paper among them, with
    no page (D95); None when it is linked to none of them."""
    anchor = _first_anchor(note, paper_ids)
    if anchor is not None:
        return NoteSource(id=note.id, paper_id=anchor.paper_id, page=anchor.page, provenance=note.provenance)
    paper_id = next((pid for pid in note.paper_ids if pid in paper_ids), None)
    if paper_id is None:
        return None
    return NoteSource(id=note.id, paper_id=paper_id, page=None, provenance=note.provenance)


def format_notes_block(notes: list[NoteView], papers: dict[uuid.UUID, Paper]) -> tuple[str, list[NoteSource]]:
    """One [N{i}] line per note, newest first, while the block fits NOTES_CHAR_BUDGET. A line is never split.

    A note with a passage on one of `papers` is named by its first one, with its page and quote. A note with none there
    is named by its first linked paper among them, with no page or quote, and left out if it has no body either.
    Returns the block and the notes it holds (N{i} is the i-th).
    """
    lines: list[str] = []
    used: list[NoteSource] = []
    for note in sorted(notes, key=lambda n: n.updated_at, reverse=True):
        source, anchor = _source(note, papers), _first_anchor(note, papers)
        # A promoted AI note's body/quote is a verbatim answer slice and may still carry that answer's own
        # [C#]/[N#] markers; strip them first so the model can't echo one that now points elsewhere.
        body = _cut(_CITATION.sub("", note.body), NOTE_BODY_CHARS)
        if source is None or (anchor is None and not body):
            continue
        where = source_label(papers[source.paper_id]) + ("" if source.page is None else f" p.{source.page}")
        line = f"[N{len(lines) + 1}] ({BADGES[note.provenance]} · {where})"
        if anchor is not None:
            line += f' "{_cut(_CITATION.sub("", anchor.quoted_text), NOTE_QUOTE_CHARS)}"'
        if body:
            line += f" — {body}"
        if sum(map(len, lines)) + len(lines) + len(line) > NOTES_CHAR_BUDGET:  # len(lines): the newlines
            break
        lines.append(line)
        used.append(source)
    return "\n".join(lines), used


async def _prepare_workspace(session: AsyncSession, workspace_id: uuid.UUID, question: str, embedder) -> Prepared:
    """Retrieved passages across the workspace's papers plus all its notes, trimmed. No whole-paper skip.

    Raises NotFound, or Conflict("workspace_empty" | "search_not_set_up" | "search_rebuilding" |
    "embedding_model_changed" | "workspace_not_indexed").
    """
    members = {p.id: p for p in await workspaces.papers(session, workspace_id)}
    if not members:
        raise Conflict("workspace_empty")
    ready = [paper_id for paper_id, paper in members.items() if paper.status == PaperStatus.READY]
    # D156's gate before the index: not set up, then rebuilding, then vectors from another model.
    embedder = await searchable(session, ready, embedder)
    if not await session.scalar(select(func.count(Chunk.embedding)).where(Chunk.paper_id.in_(ready))):
        raise Conflict("workspace_not_indexed")
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

    Raises NotFound, or Conflict("paper_not_ready" | "search_not_set_up" | "search_rebuilding" |
    "embedding_model_changed" | "paper_not_indexed"). A small paper needs no search model.
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
        # D156's gate before the index: not set up, then rebuilding, then vectors from another model.
        embedder = await searchable(session, [paper_id], embedder)
        if embedded == 0:  # ingested before M4, or before the model arrived: the UI offers Re-index
            raise Conflict("paper_not_indexed")
    if whole_paper:
        sources = await chunk_sources(session, Chunk.paper_id == paper_id)
    else:
        sources = await retrieve(session, question, paper_ids=[paper_id], k=RETRIEVE_K, embedder=embedder)
        if thread is not None:
            sources = follow_up_sources(await _earlier_sources(session, thread, paper_id), sources)
    every_note = await list_notes_for_paper(session, paper_id)
    block, used = format_notes_block(every_note, {paper_id: paper})
    context = format_context(paper, sources)
    earlier = _earlier_block(thread)
    prompt = PROMPT_TEMPLATE.format(
        context=context, notes=block or NO_NOTES_PLACEHOLDER, earlier=earlier, question=question
    )
    return Prepared(
        sources=sources,
        system=SYSTEM_PROMPT,
        prompt=prompt,
        whole_paper=whole_paper,
        notes=used,
        notes_total=len(every_note),
    )


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
    saved_papers = await papers_of(session, [note_id for *_, note_id in saved])
    saved_notes: dict[uuid.UUID, list[SavedNote]] = {}
    for output_id, index, note_id in saved:
        saved_notes.setdefault(output_id, []).append(SavedNote(index, note_id, saved_papers.get(note_id, [])))
    return [
        Answer(
            output=o,
            sources=[chunks.get(chunk_id) for chunk_id in o.source_chunks],
            # None: the note was deleted, or is no longer linked to a paper in scope (spec §4.3).
            notes=[None if note_id not in by_id else _source(by_id[note_id], members) for note_id in o.source_notes],
            saved_notes=saved_notes.get(o.id, []),
        )
        for o in outputs
    ]
