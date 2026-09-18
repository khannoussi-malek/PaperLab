import logging
import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LLMDep, SessionDep
from app.core import chat
from app.core.errors import Conflict
from app.core.retrieval import RetrievedChunk
from app.db import SessionLocal
from app.providers.base import LLM, LLMError, LLMUnavailable
from app.schemas.chat import (
    ChatAnswer,
    ChatRequest,
    ChatSource,
    DoneEvent,
    ErrorEvent,
    NoteSource,
    SourcesEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def _prepare(
    session: AsyncSession, scope: chat.Scope, question: str, thread: chat.Thread | None = None
) -> chat.Prepared:
    """Runs before the stream starts: once an SSE response has begun, an exception only drops the connection."""
    prepared = await chat.prepare(session, scope, question, thread=thread)
    # End the transaction now. The LLM stream can take minutes and must not hold a pooled connection.
    await session.commit()
    return prepared


async def prepare_answer(paper_id: uuid.UUID, payload: ChatRequest, session: SessionDep) -> chat.Prepared:
    thread = None if payload.parent_id is None else await chat.load_thread(session, paper_id, payload.parent_id)
    return await _prepare(session, chat.Scope(paper_id=paper_id), payload.question, thread)


async def prepare_workspace_answer(
    workspace_id: uuid.UUID, payload: ChatRequest, session: SessionDep
) -> chat.Prepared:
    if payload.parent_id is not None:
        raise Conflict("follow_ups_paper_only")  # D62: until workspace follow-ups are measured
    return await _prepare(session, chat.Scope(workspace_id=workspace_id), payload.question)


PreparedDep = Annotated[chat.Prepared, Depends(prepare_answer)]
WorkspacePreparedDep = Annotated[chat.Prepared, Depends(prepare_workspace_answer)]


def to_sources(chunks: list[RetrievedChunk | None]) -> list[ChatSource | None]:
    return [
        None
        if c is None
        else ChatSource(label=f"C{i}", chunk_id=c.id, paper_id=c.paper_id, page=c.page, section=c.section, bbox=c.bbox)
        for i, c in enumerate(chunks, start=1)
    ]


def to_notes(notes: list[chat.NoteSource | None]) -> list[NoteSource | None]:
    return [
        None
        if n is None
        else NoteSource(label=f"N{i}", note_id=n.id, paper_id=n.paper_id, page=n.page, provenance=n.provenance)
        for i, n in enumerate(notes, start=1)
    ]


def error_event(message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=ErrorEvent(message=message, retryable=True))


# The route yields ServerSentEvent, so FastAPI can't see the payload models; listing them here puts
# them in OpenAPI components, where openapi-typescript generates their types.
STREAM_RESPONSES = {200: {"model": SourcesEvent | TokenEvent | DoneEvent | ErrorEvent}}


async def answer_events(
    scope: chat.Scope, question: str, prepared: chat.Prepared, llm: LLM, parent_id: uuid.UUID | None = None
) -> AsyncIterable[ServerSentEvent]:
    """Events: sources, token (repeated), then done. error replaces done, and then nothing is saved."""
    sources = SourcesEvent(
        whole_paper=prepared.whole_paper,
        sources=to_sources(prepared.sources),
        notes=to_notes(prepared.notes),
        notes_used=prepared.notes_used,
        notes_total=prepared.notes_total,
    )
    yield ServerSentEvent(event="sources", data=sources)
    parts: list[str] = []
    try:
        async for text in llm.stream(prepared.system, prepared.prompt):
            parts.append(text)
            yield ServerSentEvent(event="token", data=TokenEvent(text=text))
    except (LLMUnavailable, LLMError) as exc:
        # The message names the connection and host, never the key (providers mask it).
        logger.warning("chat answer on %s (%s) failed: %s", llm.connection_name, llm.host, exc)
        yield error_event(str(exc))
        return
    except Exception:
        logger.exception("chat answer on %s (%s) failed unexpectedly", llm.connection_name, llm.host)
        yield error_event("The answer stopped because of an unexpected error")
        return

    content = "".join(parts)
    try:
        async with SessionLocal() as session:
            output_id = await chat.save_answer(
                session, scope, question, prepared, content, llm.model, llm.connection_name, parent_id
            )
    except Exception:
        logger.exception("saving a chat answer for %s failed", scope)
        yield error_event("The answer couldn't be saved")
        return

    cited = [f"C{i}" for i in chat.parse_citations(content, len(prepared.sources))]
    cited += [f"N{i}" for i in chat.parse_citations(content, len(prepared.notes), "N")]
    done = DoneEvent(
        output_id=output_id,
        model=llm.model,
        connection_name=llm.connection_name,
        prompt_version=prepared.prompt_version,
        cited=cited,
    )
    yield ServerSentEvent(event="done", data=done)


@router.post("/api/papers/{paper_id}/chat", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def ask(
    paper_id: uuid.UUID, payload: ChatRequest, llm: LLMDep, prepared: PreparedDep
) -> AsyncIterable[ServerSentEvent]:
    """Checked before streaming, in parameter order: 404/409 for the model (llm), then 404 for the paper, 404
    parent_not_found or 409 parent_scope for a follow-up, then 409/422 for the paper."""
    async for event in answer_events(chat.Scope(paper_id=paper_id), payload.question, prepared, llm, payload.parent_id):
        yield event


@router.post("/api/workspaces/{workspace_id}/chat", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def ask_workspace(
    workspace_id: uuid.UUID, payload: ChatRequest, llm: LLMDep, prepared: WorkspacePreparedDep
) -> AsyncIterable[ServerSentEvent]:
    """Checked before streaming, in parameter order: 404 model_not_found or 409 no_model, then 409
    follow_ups_paper_only, 404, 409 workspace_empty, search_not_set_up or workspace_not_indexed, 422."""
    async for event in answer_events(chat.Scope(workspace_id=workspace_id), payload.question, prepared, llm):
        yield event


def to_answer(answer: chat.Answer) -> ChatAnswer:
    output = answer.output
    return ChatAnswer(
        id=output.id,
        question=output.question,
        content=output.content,
        model=output.model,
        connection_name=output.connection_name,
        prompt_version=output.prompt_version,
        created_at=output.created_at,
        whole_paper=output.whole_paper,
        sources=to_sources(answer.sources),
        notes=to_notes(answer.notes),
        notes_used=output.notes_used,
        notes_total=output.notes_total,
        parent_id=output.parent_id,
    )


@router.get("/api/papers/{paper_id}/chat")
async def history(paper_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return [to_answer(answer) for answer in await chat.list_answers(session, paper_id)]


@router.get("/api/workspaces/{workspace_id}/chat")
async def workspace_history(workspace_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return [to_answer(answer) for answer in await chat.list_answers(session, chat.Scope(workspace_id=workspace_id))]
