import logging
import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import SessionDep
from app.core import chat
from app.core.retrieval import RetrievedChunk
from app.db import SessionLocal
from app.providers.base import LLM, LLMError, LLMUnavailable
from app.providers.llm import get_llm
from app.schemas.chat import ChatAnswer, ChatRequest, ChatSource, DoneEvent, ErrorEvent, SourcesEvent, TokenEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers/{paper_id}/chat", tags=["chat"])

LLMDep = Annotated[LLM, Depends(get_llm)]


async def prepare_answer(paper_id: uuid.UUID, payload: ChatRequest, session: SessionDep) -> chat.Prepared:
    """Runs before the stream starts: once an SSE response has begun, an exception only drops the connection."""
    prepared = await chat.prepare(session, paper_id, payload.question)
    # End the transaction now. The LLM stream can take minutes and must not hold a pooled connection.
    await session.commit()
    return prepared


PreparedDep = Annotated[chat.Prepared, Depends(prepare_answer)]


def to_sources(chunks: list[RetrievedChunk | None]) -> list[ChatSource | None]:
    return [
        None
        if chunk is None
        else ChatSource(label=f"C{i}", chunk_id=chunk.id, page=chunk.page, section=chunk.section, bbox=chunk.bbox)
        for i, chunk in enumerate(chunks, start=1)
    ]


def error_event(message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=ErrorEvent(message=message, retryable=True))


# The route yields ServerSentEvent, so FastAPI can't see the payload models; listing them here puts
# them in OpenAPI components, where openapi-typescript generates their types.
STREAM_RESPONSES = {200: {"model": SourcesEvent | TokenEvent | DoneEvent | ErrorEvent}}


@router.post("", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def ask(
    paper_id: uuid.UUID, payload: ChatRequest, prepared: PreparedDep, llm: LLMDep
) -> AsyncIterable[ServerSentEvent]:
    """Events: sources, token (repeated), then done. error replaces done, and then nothing is saved."""
    yield ServerSentEvent(
        event="sources", data=SourcesEvent(whole_paper=prepared.whole_paper, sources=to_sources(prepared.sources))
    )
    parts: list[str] = []
    try:
        async for text in llm.stream(prepared.system, prepared.prompt):
            parts.append(text)
            yield ServerSentEvent(event="token", data=TokenEvent(text=text))
    except (LLMUnavailable, LLMError) as exc:
        yield error_event(str(exc))
        return

    content = "".join(parts)
    try:
        async with SessionLocal() as session:
            output_id = await chat.save_answer(session, paper_id, payload.question, prepared, content, llm.model)
    except Exception:
        logger.exception("saving a chat answer for paper %s failed", paper_id)
        yield error_event("The answer couldn't be saved")
        return

    cited = [f"C{i}" for i in chat.parse_citations(content, len(prepared.sources))]
    done = DoneEvent(output_id=output_id, model=llm.model, prompt_version=chat.CHAT_PROMPT_VERSION, cited=cited)
    yield ServerSentEvent(event="done", data=done)


@router.get("")
async def history(paper_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return [
        ChatAnswer(
            id=answer.output.id,
            question=answer.output.question,
            content=answer.output.content,
            model=answer.output.model,
            prompt_version=answer.output.prompt_version,
            created_at=answer.output.created_at,
            whole_paper=answer.output.whole_paper,
            sources=to_sources(answer.sources),
        )
        for answer in await chat.list_answers(session, paper_id)
    ]
