"""Chat about one search hit. With a library paper that has full text it is paper chat; otherwise it answers from
the hit's title and abstract alone.

History of abstract-only answers is kept in memory, per process, keyed by hit: LLMOutput keys on paper or workspace,
so storing by hit would need a migration. A restart forgets them; answers from full text are stored as paper chat."""

import uuid
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
HISTORY: dict[uuid.UUID, list[ChatAnswer]] = {}
NO_ABSTRACT = "(no abstract is available)"
SYSTEM_PROMPT = """You answer questions about one scientific paper. You can see only its title and abstract, not the \
full text.
Answer only from them. If they do not say, say the abstract does not cover it; do not guess.
Cite the abstract as [abstract]. Never cite page numbers or figures: you have not seen them.
Start your first answer by saying you are reading the abstract only. Be concise."""
PROMPT_TEMPLATE = "Title: {title}\n\nAbstract:\n{abstract}\n\nQuestion: {question}"


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


def prepare_abstract(context: HitContext, question: str) -> chat.Prepared:
    title = context.ref.title if context.ref else context.hit.normalized_title
    abstract = (context.ref.abstract if context.ref else None) or (context.paper.abstract if context.paper else None)
    prompt = PROMPT_TEMPLATE.format(title=title, abstract=abstract or NO_ABSTRACT, question=question)
    return chat.Prepared(
        sources=[], system=SYSTEM_PROMPT, prompt=prompt, whole_paper=True, prompt_version=HIT_PROMPT_VERSION
    )


def remember(
    hit_id: uuid.UUID, question: str, content: str, model: str, connection_name: str, parent_id: uuid.UUID | None
) -> uuid.UUID:
    answer = ChatAnswer(
        id=uuid.uuid4(), question=question, content=content, model=model, connection_name=connection_name,
        prompt_version=HIT_PROMPT_VERSION, created_at=datetime.now(timezone.utc), whole_paper=True, sources=[],
        notes=[], notes_used=None, notes_total=None, parent_id=parent_id, saved_notes=[],
    )
    HISTORY.setdefault(hit_id, []).append(answer)
    return answer.id
