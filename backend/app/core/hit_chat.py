"""Chat about one search hit. With a library paper that has full text it is paper chat; otherwise it answers from
the hit's title and abstract alone.

History of abstract-only answers is kept in memory, keyed by hit: LLMOutput keys on paper or workspace, so storing
by hit would need a migration. It is per worker process and lost on restart, and bounded (MAX_ANSWERS_PER_HIT per
hit, MAX_HITS hits, oldest hit evicted). Answers from full text are stored as paper chat."""

import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import chat
from app.core.errors import NotFound
from app.models import Paper, PaperStatus
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit
from app.schemas.chat import ChatAnswer

HIT_PROMPT_VERSION = 1
MAX_ANSWERS_PER_HIT = 20
MAX_HITS = 200
MAX_THREAD_ANSWERS = 4
EXCERPT_CHARS = 300
MAX_ABSTRACT_CHARS = 4_000
HISTORY: OrderedDict[uuid.UUID, list[ChatAnswer]] = OrderedDict()
NO_ABSTRACT = "(no abstract is available)"
SYSTEM_PROMPT = """You answer questions about one scientific paper. You can see only its title and abstract, not the \
full text.
Answer only from them. If they do not say, say the abstract does not cover it; do not guess.
Cite the abstract as [abstract]. Never cite page numbers or figures: you have not seen them.
Be concise."""
FIRST_ANSWER_NOTE = "\nStart your answer by saying you are reading the abstract only."
PROMPT_TEMPLATE = "Title: {title}\n\nAbstract:\n{abstract}\n\n{earlier}Question: {question}"


@dataclass(frozen=True)
class HitContext:
    hit: WorkspaceSearchHit
    ref: ExternalRef | None
    paper: Paper | None

    @property
    def source(self) -> Literal["abstract", "full_text"]:
        paper = self.paper
        ready = paper is not None and paper.has_chunks and paper.status in (PaperStatus.READY, PaperStatus.EMBEDDING)
        return "full_text" if ready else "abstract"


async def load(session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID) -> HitContext:
    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found")
    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    paper = await session.get(Paper, hit.paper_id) if hit.paper_id else None
    return HitContext(hit, ref, paper)


def thread_for(hit_id: uuid.UUID, parent_id: uuid.UUID) -> list[ChatAnswer]:
    """The parent and up to MAX_THREAD_ANSWERS - 1 answers before it, oldest first. Raises NotFound("parent_not_found")."""
    by_id = {a.id: a for a in HISTORY.get(hit_id, [])}
    chain = []
    next_id = parent_id
    while next_id in by_id and len(chain) < MAX_THREAD_ANSWERS:
        chain.append(by_id[next_id])
        next_id = by_id[next_id].parent_id
    if not chain:
        raise NotFound("parent_not_found")
    return chain[::-1]


def _earlier_block(thread: list[ChatAnswer]) -> str:
    items = "".join(f"- {a.question}\n  Answer began: {a.content[:EXCERPT_CHARS]}\n" for a in thread)
    return f"Earlier questions in this conversation, oldest first:\n{items}\n"


def prepare_abstract(context: HitContext, question: str, parent_id: uuid.UUID | None = None) -> chat.Prepared:
    title = context.ref.title if context.ref else context.hit.normalized_title
    abstract = (context.ref.abstract if context.ref else None) or (context.paper.abstract if context.paper else None)
    thread = [] if parent_id is None else thread_for(context.hit.id, parent_id)
    prompt = PROMPT_TEMPLATE.format(
        title=title, abstract=(abstract or NO_ABSTRACT)[:MAX_ABSTRACT_CHARS],
        earlier=_earlier_block(thread) if thread else "", question=question,
    )
    system = SYSTEM_PROMPT + ("" if thread else FIRST_ANSWER_NOTE)
    return chat.Prepared(sources=[], system=system, prompt=prompt, whole_paper=True, prompt_version=HIT_PROMPT_VERSION)


def remember(
    hit_id: uuid.UUID, question: str, content: str, model: str, connection_name: str, parent_id: uuid.UUID | None
) -> uuid.UUID:
    answer = ChatAnswer(
        id=uuid.uuid4(), question=question, content=content, model=model, connection_name=connection_name,
        prompt_version=HIT_PROMPT_VERSION, created_at=datetime.now(timezone.utc), whole_paper=True, sources=[],
        notes=[], notes_used=None, notes_total=None, parent_id=parent_id, saved_notes=[],
    )
    answers = HISTORY.setdefault(hit_id, [])
    answers.append(answer)
    del answers[:-MAX_ANSWERS_PER_HIT]
    HISTORY.move_to_end(hit_id)
    while len(HISTORY) > MAX_HITS:
        HISTORY.popitem(last=False)
    return answer.id
