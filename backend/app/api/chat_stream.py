"""Streaming a chat answer as Server-Sent Events, saving it at the end, and the per-paper events of Ask each paper."""

import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable

from fastapi.sse import ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import chat, chat_answers, each_paper
from app.db import SessionLocal
from app.providers.base import LLM, LLMError, LLMUnavailable
from app.schemas.chat import DoneEvent, ErrorEvent, ReadingEvent, SourcesEvent, TokenEvent, to_notes, to_sources

logger = logging.getLogger(__name__)

def error_event(message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=ErrorEvent(message=message, retryable=True))


NO_TEXT_TO_READ = "None of these papers has text to read"
NOTHING_READ = "The model couldn't read any of these papers"


Save = Callable[[AsyncSession, str], Awaitable[uuid.UUID]]


def _sources_event(prepared: chat.Prepared) -> SourcesEvent:
    return SourcesEvent(
        whole_paper=prepared.whole_paper,
        sources=to_sources(prepared.sources),
        notes=to_notes(prepared.notes),
        notes_used=prepared.notes_used,
        notes_total=prepared.notes_total,
    )


def _done_event(prepared: chat.Prepared, llm: LLM, content: str, output_id: uuid.UUID) -> DoneEvent:
    """The finished output, with the sources and notes its text cites."""
    cited = [f"C{i}" for i in chat_answers.parse_citations(content, len(prepared.sources))]
    cited += [f"N{i}" for i in chat_answers.parse_citations(content, len(prepared.notes), "N")]
    return DoneEvent(
        output_id=output_id,
        model=llm.model,
        connection_name=llm.connection_name,
        prompt_version=prepared.prompt_version,
        cited=cited,
        skill_label=prepared.skill_label,
        lens=prepared.lens,
    )


async def stream_output(
    prepared: chat.Prepared, llm: LLM, save: Save, noun: str, log_as: str, log_for: object
) -> AsyncIterable[ServerSentEvent]:
    """Events: sources, token (repeated), then done. error replaces done, and then nothing is saved.

    `save` stores the finished text in a fresh session and returns its id; `noun` names the output in the error texts
    ("answer", "brief") and `log_as` in the logs ("chat answer", "brief"), because chat's tests assert its log text;
    `log_for` names what a failed save was for (chat's scope, a brief's paper and lens).
    Shared by chat and M16's briefs (and M22's check, D175)."""
    yield ServerSentEvent(event="sources", data=_sources_event(prepared))
    parts: list[str] = []
    try:
        async for text in llm.stream(prepared.system, prepared.prompt):
            parts.append(text)
            yield ServerSentEvent(event="token", data=TokenEvent(text=text))
    except (LLMUnavailable, LLMError) as exc:
        # The message names the connection and host, never the key (providers mask it).
        logger.warning("%s on %s (%s) failed: %s", log_as, llm.connection_name, llm.host, exc)
        yield error_event(str(exc))
        return
    except Exception:
        logger.exception("%s on %s (%s) failed unexpectedly", log_as, llm.connection_name, llm.host)
        yield error_event(f"The {noun} stopped because of an unexpected error")
        return

    content = "".join(parts)
    try:
        async with SessionLocal() as session:
            output_id = await save(session, content)
    except Exception:
        logger.exception("saving a %s for %s failed", log_as, log_for)
        yield error_event(f"The {noun} couldn't be saved")
        return

    yield ServerSentEvent(event="done", data=_done_event(prepared, llm, content, output_id))


async def answer_events(
    scope: chat.Scope, question: str, prepared: chat.Prepared, llm: LLM, parent_id: uuid.UUID | None = None
) -> AsyncIterable[ServerSentEvent]:
    """A chat answer's stream (stream_output), saved as a chat answer."""

    async def save(session: AsyncSession, content: str) -> uuid.UUID:
        return await chat_answers.save_answer(
            session, scope, question, prepared, chat_answers.Reply(content, llm.model, llm.connection_name), parent_id
        )

    async for event in stream_output(prepared, llm, save, "answer", "chat answer", scope):
        yield event


async def each_paper_events(
    scope: chat.Scope, question: str, plan: each_paper.Plan, llm: LLM
) -> AsyncIterable[ServerSentEvent]:
    """M8.5: a reading event per paper as its record lands, then the answer from the records as chat streams one.
    No paper read (all without text, or the model failing on every one): an error, nothing saved."""
    readings: list[each_paper.Reading] = []
    async for reading in each_paper.read_all(question, plan.tasks, llm):
        readings.append(reading)
        yield ServerSentEvent(
            event="reading",
            data=ReadingEvent(
                paper_id=reading.paper_id, label=reading.label, status=reading.status, answer=reading.answer,
                cited=[c.id for c in reading.cited], low_confidence=reading.low_confidence, cached=reading.cached,
                done=len(readings), total=len(plan.tasks),
            ),
        )
    if not any(r.status in ("found", "absent") for r in readings):
        textless = all(r.status == "no_text" for r in readings)
        yield error_event(NO_TEXT_TO_READ if textless else NOTHING_READ)
        return
    async for event in answer_events(scope, question, each_paper.reduce_prepared(plan, readings), llm):
        yield event
