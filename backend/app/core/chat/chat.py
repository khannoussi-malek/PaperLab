"""Chat over one paper or one workspace: choose the sources, build the prompt, store answers.

Never writes notes: an answer becomes a note through notes.promote_llm_fragment or notes.save_suggestion, both a
click by the reader.
"""

import uuid
from dataclasses import dataclass, field
from itertools import accumulate

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat.chat_context import NoteSource, format_context, format_notes_block
from app.core.chat.retrieval import RetrievedChunk, _to_chunk, likely_papers, retrieve, searchable
from app.core.notes.notes import (
    list_notes_for_paper,
)
from app.core.papers import lenses
from app.core.papers.papers import get_paper
from app.core.platform import prompts, skills
from app.core.workspaces import workspaces
from app.domain.errors import Conflict, NotFound
from app.models import Chunk, LLMOutput, Paper, PaperStatus

# v6: the note-block rule leads with its condition and names "never" explicitly, to stop it firing on an unasked
# follow-up; v5: a literal example fixed the delimiter syntax; v4: asked for notes, the model writes each as a
# :::note block (M20)
CHAT_PROMPT_VERSION = 7  # v7: cite only the labels listed (M72)
WORKSPACE_PROMPT_VERSION = 6  # v6: the same cite-only-listed rule
# Each file holds the system prompt, then the user prompt template after this marker line.
PROMPT_MARKER = "\n<!-- prompt -->\n"
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat", CHAT_PROMPT_VERSION).split(PROMPT_MARKER)
WORKSPACE_SYSTEM_PROMPT, WORKSPACE_PROMPT_TEMPLATE = prompts.load("chat_workspace", WORKSPACE_PROMPT_VERSION).split(
    PROMPT_MARKER
)
# ponytail: characters stand in for tokens. Revisit with the eval numbers or a model's real context size.
SMALL_PAPER_CHARS = 24_000
FULL_LENS = skills.FULL  # a skill whose lens is the whole paper, or no skill: sources as before M16 lens chat
RETRIEVE_K = 8
# What a long paper's retrieval hands to cut_to_budget: as many passages as fit what a whole small paper may send. About
# 12 on real chunks, and on fixed-answer questions 29 of 33 with hybrid against 28 at top 8 (measured 2026-11-04).
# ponytail: the same budget for every model; 60,000 characters answered 31 of 33, but a cloud model pays per question.
RETRIEVE_POOL = 40
# A follow-up's earlier passages plus fresh ones: ~4.5k tokens, so with notes it still fits OLLAMA_NUM_CTX.
FOLLOW_UP_SOURCES = 12
# A follow-up carries its parent answer's question and passages, and those of at most four answers before it.
MAX_THREAD_ANSWERS = 5
# A bare "(none)" here once got parroted back as an answer's entire content by a small local model asked a
# question that itself mentioned "notes" — a short, quotable placeholder sitting right above "Question: ..." reads
# too much like a plausible answer to a weak model. A full sentence doesn't.
NO_NOTES_PLACEHOLDER = "No notes have been written yet."
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
class Prepared:
    sources: list[RetrievedChunk]  # C{i} is sources[i-1]
    system: str
    prompt: str
    whole_paper: bool
    prompt_version: int = CHAT_PROMPT_VERSION
    notes: list[NoteSource] = field(default_factory=list)  # N{i} is notes[i-1]
    notes_total: int | None = None  # every note in the paper or workspace
    skill_label: str | None = None  # the skill the question ran with, copied onto the answer (M17)
    skill_version: int | None = None
    lens: str = FULL_LENS  # the lens the sources came from; 'full' unless the skill's lens had sections here (M16)
    readings: list[uuid.UUID] = field(default_factory=list)  # Ask each paper: the per-paper records (M8.5)

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


async def chunk_sources(session: AsyncSession, *where) -> list[RetrievedChunk]:
    rows = await session.execute(select(*_SOURCE_COLUMNS).where(*where).order_by(Chunk.ordinal))
    return [_to_chunk(row) for row in rows]


async def lens_sources(session: AsyncSession, paper_id: uuid.UUID, lens: str) -> list[RetrievedChunk]:
    """A lens's chunks in one paper, in reading order: [] when the paper has no sections for the lens."""
    found = await lenses.lens_chunks(session, paper_id, lens)
    if not found.chunk_ids:
        return []
    return await chunk_sources(session, Chunk.id.in_(found.chunk_ids))


def _lens_of(skill: skills.SkillView | None) -> str:
    return FULL_LENS if skill is None else skill.lens


def _fits(sources: list[RetrievedChunk]) -> bool:
    """Whether every one of `sources` fits the budget together (cut_to_budget keeps an oversized first chunk; this
    doesn't count it as fitting)."""
    return bool(sources) and sum(len(source.text) for source in sources) <= SMALL_PAPER_CHARS


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


def cut_to_budget(sources: list[RetrievedChunk], budget: int = SMALL_PAPER_CHARS) -> list[RetrievedChunk]:
    """The longest start of `sources`, in their order, whose text fits `budget` characters. A chunk is never split,
    and the first one is always kept, so a brief never reads nothing."""
    totals = accumulate(len(source.text) for source in sources)
    return [source for source, total in zip(sources, totals) if total <= budget] or sources[:1]


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


async def _workspace_sources(
    session: AsyncSession, ready: list[uuid.UUID], question: str, embedder, lens: str
) -> tuple[list[RetrievedChunk], bool, str]:
    """(sources, whole, lens used). A skill's lens gives the union of every ready paper's lens chunks: all of them when
    they fit, else the nearest that fit, drawn from that union. With no lens or no sections, the whole library's
    passages as before."""
    lens_chunks: list[RetrievedChunk] = []
    if lens != FULL_LENS:
        for paper_id in ready:
            lens_chunks += await lens_sources(session, paper_id, lens)
    if _fits(lens_chunks):
        return lens_chunks, True, lens
    if lens_chunks:
        found = await retrieve(
            session,
            question,
            paper_ids=ready,
            k=RETRIEVE_POOL,
            embedder=embedder,
            words=True,
            chunk_ids=[c.id for c in lens_chunks],
        )
        return cut_to_budget(found), False, lens
    # ponytail: the question is embedded twice, once per search; pass the vector along if it ever shows in the timings.
    scope = await likely_papers(session, question, ready, embedder)
    found = await retrieve(session, question, paper_ids=scope, k=RETRIEVE_POOL, embedder=embedder, words=True)
    return cut_to_budget(found), False, FULL_LENS


async def _prepare_workspace(
    session: AsyncSession, workspace_id: uuid.UUID, question: str, embedder, skill: skills.SkillView | None = None
) -> Prepared:
    """Retrieved passages across the workspace's papers plus all its notes, trimmed. No whole-paper skip, unless a
    skill's lens fits whole.

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
    sources, whole, lens = await _workspace_sources(session, ready, question, embedder, _lens_of(skill))
    every_note = await workspaces.notes(session, workspace_id)
    block, used = format_notes_block(every_note, members)
    prompt = WORKSPACE_PROMPT_TEMPLATE.format(
        context=format_context(members, sources), notes=block or NO_NOTES_PLACEHOLDER, question=question
    )
    return Prepared(
        sources=sources,
        system=skills.compose(WORKSPACE_SYSTEM_PROMPT, skill),
        prompt=prompt,
        whole_paper=whole and lens == FULL_LENS,  # the whole lens is not the whole workspace: keep each cite pill
        prompt_version=WORKSPACE_PROMPT_VERSION,
        notes=used,
        notes_total=len(every_note),
        lens=lens,
        **_skill_fields(skill),
    )


def _skill_fields(skill: skills.SkillView | None) -> dict:
    return {} if skill is None else {"skill_label": skill.label, "skill_version": skill.version}


async def prepare(
    session: AsyncSession,
    paper_id: uuid.UUID | Scope,
    question: str,
    embedder=None,
    thread: Thread | None = None,
    skill: skills.SkillView | None = None,
) -> Prepared:
    """A workspace scope goes to _prepare_workspace. For a paper: small papers go whole, in reading order; larger ones
    send the nearest chunks that fit SMALL_PAPER_CHARS. The paper's notes follow, newest first, as in workspace chat.
    A follow-up (`thread`) adds the earlier questions, and a large paper's earlier passages ahead of the fresh ones.

    Raises NotFound, or Conflict("paper_not_ready" | "search_not_set_up" | "search_rebuilding" |
    "embedding_model_changed" | "paper_not_indexed" | "no_text" | "nothing_found_yet"). A small paper needs no search
    model.
    """
    scope = _scope(paper_id)
    if scope.workspace_id is not None:
        if thread is not None:
            # ponytail: follow-ups are measured on paper chat first; workspace chat gets them if they earn their keep.
            raise ValueError("follow-ups are paper chat only for now")
        return await _prepare_workspace(session, scope.workspace_id, question, embedder, skill)
    paper_id = scope.paper_id
    paper = await get_paper(session, paper_id)
    if paper.status not in (PaperStatus.READY, PaperStatus.EMBEDDING):  # embedding: retrieve answers from its words
        raise Conflict("paper_not_ready")
    chars, embedded = await _size(session, paper_id)
    if chars == 0 and not paper.has_pdf:  # saved without a PDF or an abstract: nothing to answer from, no LLM call
        raise Conflict("no_text")
    # A skill's lens (M16) replaces the paper: its chunks whole when they fit, else the nearest of them that fit.
    lens = _lens_of(skill)
    lens_chunks = await lens_sources(session, paper_id, lens) if lens != FULL_LENS else []
    lens_fits = _fits(lens_chunks)
    whole_paper = lens_fits or (not lens_chunks and chars <= SMALL_PAPER_CHARS)
    if not whole_paper:
        # D156's gate before the index: not set up, then rebuilding, then vectors from another model.
        embedder = await searchable(session, [paper_id], embedder)
        if embedded == 0 and paper.status == PaperStatus.READY:  # before M4 or the model: the UI offers Re-index
            raise Conflict("paper_not_indexed")
    if lens_fits:
        sources = lens_chunks
    elif whole_paper:
        sources = await chunk_sources(session, Chunk.paper_id == paper_id)
    else:
        chunk_ids = [c.id for c in lens_chunks] or None  # no lens sections: the whole paper, as before
        found = await retrieve(
            session, question, paper_ids=[paper_id], k=RETRIEVE_POOL, embedder=embedder, chunk_ids=chunk_ids
        )
        if thread is None:
            sources = cut_to_budget(found)
            if not sources:  # no vectors yet and no matching word: the model would answer from nothing
                raise Conflict("nothing_found_yet")
        else:  # the fresh ones are kept whole, so more of them would push out the conversation's earlier passages
            sources = follow_up_sources(await _earlier_sources(session, thread, paper_id), found[:RETRIEVE_K])
    every_note = await list_notes_for_paper(session, paper_id)
    block, used = format_notes_block(every_note, {paper_id: paper})
    context = format_context(paper, sources)
    earlier = _earlier_block(thread)
    prompt = PROMPT_TEMPLATE.format(
        context=context, notes=block or NO_NOTES_PLACEHOLDER, earlier=earlier, question=question
    )
    return Prepared(
        sources=sources,
        system=skills.compose(SYSTEM_PROMPT, skill),
        prompt=prompt,
        whole_paper=whole_paper and not lens_chunks,  # the whole lens is not the whole paper
        notes=used,
        notes_total=len(every_note),
        lens=lens if lens_chunks else FULL_LENS,
        **_skill_fields(skill),
    )


