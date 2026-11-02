"""The exit-test check (M22 §3.7): a note against its paper, streamed as the lines that survive the rules (D118)."""

import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import STREAM_RESPONSES, stream_output, to_sources
from app.api.deps import CheckLLMDep, SessionDep
from app.core import checks
from app.schemas.checks import CheckLineOut, CheckOut

router = APIRouter(tags=["checks"])


async def prepare_check(note_id: uuid.UUID, session: SessionDep) -> checks.PreparedCheck:
    """Runs before the stream starts, like chat's: once an SSE response has begun, an exception only drops it."""
    check = await checks.prepare_check(session, note_id)
    await session.commit()  # the model can take minutes, and must not hold a pooled connection meanwhile
    return check


CheckPreparedDep = Annotated[checks.PreparedCheck, Depends(prepare_check)]


@router.post("/api/notes/{note_id}/check", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def check_note(note_id: uuid.UUID, llm: CheckLLMDep, check: CheckPreparedDep) -> AsyncIterable[ServerSentEvent]:
    """Chat's events, but a token is one kept line and `cited` comes from kept lines alone. Checked before streaming,
    in order: 404 model_not_found / 409 no_model / 409 remote_model_needs_confirm (the model the body names), 404 note,
    409 not_your_text, 422 not_checkable, 422 nothing_written, 422 note_too_long, 409 note_not_on_one_paper, 409
    needs_full_text, 409 paper_not_ready, 409 lens_empty, 409 search_not_set_up, 409 search_rebuilding, 409
    paper_not_indexed, 409 embedding_model_changed."""
    kept = checks.KeptLines(llm, len(check.prepared.sources), check.guard)

    async def save(session: AsyncSession, _content: str) -> uuid.UUID:
        return await checks.save_check(session, check, kept.raw, llm.model, llm.connection_name)

    async for event in stream_output(check.prepared, kept, save, "check", "check", f"note {note_id}"):
        yield event


@router.get("/api/papers/{paper_id}/checks")
async def list_checks(paper_id: uuid.UUID, session: SessionDep) -> list[CheckOut]:
    """The newest check per note, each saying whether its note changed since. 404 (410 merged) for the paper."""
    return [
        CheckOut(
            id=view.output.id,
            note_id=view.note_id,
            lines=[CheckLineOut(verdict=line.verdict, text=line.text) for line in view.lines],
            dropped=view.dropped,
            sources=to_sources(view.sources),
            whole_paper=view.output.whole_paper,
            model=view.output.model,
            connection_name=view.output.connection_name,
            prompt_version=view.output.prompt_version,
            created_at=view.output.created_at,
            stale=view.stale,
        )
        for view in await checks.list_checks(session, paper_id)
    ]
