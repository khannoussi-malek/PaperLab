"""AI briefs (M16 L7): one lens of one paper, summarised on demand, streamed like a chat answer, saved on done."""

import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import STREAM_RESPONSES, stream_output, to_sources
from app.api.deps import LLMByModelIdDep, SessionDep
from app.core import briefs, chat
from app.core.lenses import LensId
from app.schemas.lenses import BriefOut

router = APIRouter(prefix="/api/papers", tags=["briefs"])


async def prepare_brief(paper_id: uuid.UUID, lens: LensId, session: SessionDep) -> chat.Prepared:
    """Runs before the stream starts, like chat's: once an SSE response has begun, an exception only drops it."""
    prepared = await briefs.prepare_brief(session, paper_id, lens)
    await session.commit()  # the model can take minutes, and must not hold a pooled connection meanwhile
    return prepared


BriefPreparedDep = Annotated[chat.Prepared, Depends(prepare_brief)]


@router.post("/{paper_id}/briefs/{lens}", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def generate_brief(
    paper_id: uuid.UUID, lens: LensId, llm: LLMByModelIdDep, prepared: BriefPreparedDep
) -> AsyncIterable[ServerSentEvent]:
    """Chat's events; no body, the model is the optional `?model_id=`. Checked before streaming, in parameter order:
    404 model_not_found or 409 no_model, 422 for an unknown lens or bad model_id, then 404 for the paper, 422
    lens_not_briefable, 409 needs_full_text (no PDF), paper_not_ready or lens_empty."""

    async def save(session: AsyncSession, content: str) -> uuid.UUID:
        return await briefs.save_brief(session, paper_id, lens, prepared, content, llm.model, llm.connection_name)

    async for event in stream_output(prepared, llm, save, "brief", "brief"):
        yield event


def to_brief(brief: briefs.Brief) -> BriefOut:
    output = brief.output
    return BriefOut(
        id=output.id,
        lens=output.lens,
        content=output.content,
        model=output.model,
        connection_name=output.connection_name,
        prompt_version=output.prompt_version,
        created_at=output.created_at,
        stale=brief.stale,
        partial=not output.whole_paper,
        sources=to_sources(brief.sources),
    )


@router.get("/{paper_id}/briefs")
async def list_briefs(paper_id: uuid.UUID, session: SessionDep) -> list[BriefOut]:
    """The newest brief per lens, each saying whether it is out of date. 404 for an unknown paper."""
    return [to_brief(brief) for brief in await briefs.list_briefs(session, paper_id)]
