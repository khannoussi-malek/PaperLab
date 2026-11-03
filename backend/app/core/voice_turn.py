"""One voice turn: a spoken question to a streamed, spoken answer, timed, and saved once the reader has heard it.

run_turn fills a TurnResult as it goes, so a turn cancelled mid-answer still shows what was sent. It saves nothing to
llm_outputs: finish_whole (all of it played) or save_heard (cut off) does, and each writes the one timing row.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import chat
from app.core.errors import Conflict, DomainError, error_code
from app.core.voice_text import SentenceSplitter, heard_text, speakable
from app.db import SessionLocal
from app.models.voice_turn import VoiceTurn
from app.providers.base import LLM, LLMError, LLMUnavailable, Speech, SpeechUnavailable
from app.providers.embedding import query_embed_ms
from app.schemas.chat import SourcesEvent, to_notes, to_sources

logger = logging.getLogger(__name__)

Send = Callable[[dict | bytes], Awaitable[None]]

CUT_OFF = "…"
UNEXPECTED = "The answer stopped because of an unexpected error"
CANNOT_ANSWER = "This question can't be answered right now."
# (message, retryable): the words typed chat's panel gives each refusal (frontend/src/features/chat/refusals.ts).
REFUSALS = {
    "not_found": ("That paper couldn't be found.", False),
    "paper_not_ready": ("This paper is still being processed. Ask again once it is ready.", True),
    "paper_not_indexed": ("This paper was added before chat existed, so it has no search index yet.", False),
    "no_text": ("This paper has no PDF and no abstract to chat with.", False),
    "search_not_set_up": ("Search isn't set up, so this can't be searched yet.", False),
    "search_rebuilding": ("Search is being rebuilt.", True),
    "workspace_empty": ("Add papers to chat with this workspace.", False),
    "workspace_not_indexed": (
        "None of this workspace's papers can be searched yet. Ask again once they finish processing.",
        True,
    ),
    "embedding_model_changed": (
        "Your library was indexed with a different embedding model. Re-index it to chat again.",
        False,
    ),
    "parent_not_found": ("The answer you were following is gone. Ask again to start a new question.", False),
    "parent_scope": ("The answer you were following is gone. Ask again to start a new question.", False),
    "follow_ups_paper_only": ("Follow-up questions work with one paper at a time.", False),
}


@dataclass
class TurnResult:
    """Made by the caller, filled by run_turn. `chunks` holds what was sent as audio, in order: (text, seconds)."""

    scope: chat.Scope
    cold: bool = False
    parent_id: uuid.UUID | None = None
    turn_id: uuid.UUID = field(default_factory=uuid.uuid4)
    question: str = ""
    chunks: list[tuple[str, float]] = field(default_factory=list)
    answer: str = ""  # the raw tokens joined, so whole answers keep their line breaks
    prepared: chat.Prepared | None = None
    timing: dict[str, int] = field(default_factory=dict)  # VoiceTurn columns measured here
    row_id: uuid.UUID | None = None


def _ms(began: float, now: float | None = None) -> int:
    return round(((perf_counter() if now is None else now) - began) * 1000)


def _first(exc: BaseException) -> BaseException:
    """The failure inside a TaskGroup's ExceptionGroup."""
    while isinstance(exc, BaseExceptionGroup):
        exc = exc.exceptions[0]
    return exc


async def run_turn(result: TurnResult, samples: bytes, llm: LLM, speech: Speech, send: Send) -> None:
    """Sends turn, transcript, sources, then token and sentence+audio messages, then done; or error instead of done."""
    started = perf_counter()
    await send({"type": "turn", "id": str(result.turn_id)})
    try:
        result.question = (await speech.transcribe(samples)).strip()
        result.timing["stt_ms"] = _ms(started)
        if not result.question:  # noise: no model call, no row
            await send({"type": "done"})
            return
        await send({"type": "transcript", "text": result.question})
        prepared = await _prepare(result)
        await send({"type": "sources", **_sources_event(prepared).model_dump(mode="json")})
        await _stream_and_speak(result, prepared, llm, speech, send, started)
    except Exception as exc:  # a TaskGroup wraps its tasks' failures in an ExceptionGroup
        await _fail(result, llm, send, _first(exc))
        return
    await send({"type": "done"})


async def _prepare(result: TurnResult) -> chat.Prepared:
    query_embed_ms.set(None)  # set by embed_query in this task, read back below
    async with SessionLocal() as session:  # closed before the stream: it must not hold a pooled connection
        thread = await _thread(session, result)
        began = perf_counter()
        prepared = await chat.prepare(session, result.scope, result.question, thread=thread)
        result.timing["retrieval_ms"] = _ms(began)
    if (embed_ms := query_embed_ms.get()) is not None:
        result.timing["embed_ms"] = embed_ms
    result.timing["prompt_chars"] = len(prepared.system) + len(prepared.prompt)
    result.prepared = prepared
    return prepared


async def _thread(session: AsyncSession, result: TurnResult) -> chat.Thread | None:
    if result.parent_id is None:
        return None
    if result.scope.paper_id is None:
        raise Conflict("follow_ups_paper_only")  # D62: until workspace follow-ups are measured
    return await chat.load_thread(session, result.scope.paper_id, result.parent_id)


def _sources_event(prepared: chat.Prepared) -> SourcesEvent:
    return SourcesEvent(
        whole_paper=prepared.whole_paper,
        sources=to_sources(prepared.sources),
        notes=to_notes(prepared.notes),
        notes_used=prepared.notes_used,
        notes_total=prepared.notes_total,
    )


async def _stream_and_speak(
    result: TurnResult, prepared: chat.Prepared, llm: LLM, speech: Speech, send: Send, started: float
) -> None:
    """The model's tokens feed a queue and a second task speaks its chunks, so synthesis never holds up the stream.
    One TaskGroup: a failure or a cancel in either ends both. `lock` keeps a sentence and its audio together."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    lock = asyncio.Lock()
    async with asyncio.TaskGroup() as group:
        group.create_task(_read_model(result, prepared, llm, queue, send, lock))
        group.create_task(_speak_chunks(result, speech, queue, send, lock, started))


async def _read_model(
    result: TurnResult,
    prepared: chat.Prepared,
    llm: LLM,
    queue: asyncio.Queue[str | None],
    send: Send,
    lock: asyncio.Lock,
) -> None:
    splitter = SentenceSplitter()
    began = perf_counter()
    first_token_at: float | None = None

    def queue_chunks(chunks: list[str]) -> None:
        for chunk in chunks:
            if first_token_at is not None:
                result.timing.setdefault("first_chunk_ms", _ms(first_token_at))
            queue.put_nowait(chunk)

    async for token in llm.stream(prepared.system, prepared.prompt):
        if first_token_at is None:
            first_token_at = perf_counter()
            result.timing["ttft_ms"] = _ms(began, first_token_at)
        result.answer += token
        async with lock:
            await send({"type": "token", "text": token})
        queue_chunks(splitter.feed(token))
    queue_chunks(splitter.flush())
    queue.put_nowait(None)


async def _speak_chunks(
    result: TurnResult,
    speech: Speech,
    queue: asyncio.Queue[str | None],
    send: Send,
    lock: asyncio.Lock,
    started: float,
) -> None:
    carry = ""  # chunks with nothing to say (only markers) ride along with the next spoken one
    while (chunk := await queue.get()) is not None:
        said = speakable(chunk)
        if not said:
            carry = f"{carry} {chunk}".strip()
            continue
        text, carry = f"{carry} {chunk}".strip(), ""
        began = perf_counter()
        audio, rate = await speech.speak(said)
        result.timing.setdefault("tts_first_ms", _ms(began))
        async with lock:
            await send({"type": "sentence", "seq": len(result.chunks), "text": chunk, "rate": rate})
            await send(audio)
        result.timing.setdefault("first_audio_sent_ms", _ms(started))
        result.chunks.append((text, len(audio) / 4 / rate))  # float32 samples; only once sent


def _explain(exc: BaseException, llm: LLM) -> tuple[str, bool]:
    """The reader's words for a failure, and whether asking again may help."""
    if isinstance(exc, (LLMUnavailable, LLMError)):
        # The message names the connection and host, never the key (providers mask it).
        logger.warning("voice answer on %s (%s) failed: %s", llm.connection_name, llm.host, exc)
        return str(exc), True
    if isinstance(exc, SpeechUnavailable):
        logger.warning("voice program failed: %s", exc)
        return str(exc), True
    if isinstance(exc, DomainError):
        return REFUSALS.get(error_code(exc), (CANNOT_ANSWER, False))
    logger.error("voice turn on %s (%s) failed unexpectedly", llm.connection_name, llm.host, exc_info=exc)
    return UNEXPECTED, True


async def _fail(result: TurnResult, llm: LLM, send: Send, exc: BaseException) -> None:
    message, retryable = _explain(exc, llm)
    try:
        async with SessionLocal() as session:
            await _record(session, result, llm, interrupted=False, stop_ms=None)
    except Exception:
        logger.exception("saving the timing of a failed voice turn failed")
    await send({"type": "error", "message": message, "retryable": retryable})


async def _record(
    session: AsyncSession, result: TurnResult, llm: LLM, *, interrupted: bool, stop_ms: int | None
) -> None:
    """The turn's one timing row. Nothing before a question was heard, and nothing twice."""
    if result.row_id is not None or not result.question:
        return
    row = VoiceTurn(
        paper_id=result.scope.paper_id,
        workspace_id=result.scope.workspace_id,
        model=llm.model,
        connection_name=llm.connection_name,
        cold=result.cold,
        whole_paper=result.prepared is not None and result.prepared.whole_paper,
        interrupted=interrupted,
        interrupt_stop_ms=stop_ms,
        **result.timing,
    )
    session.add(row)
    await session.commit()
    result.row_id = row.id


async def _save(session: AsyncSession, result: TurnResult, llm: LLM, content: str) -> uuid.UUID:
    assert result.prepared is not None  # nothing to save before run_turn prepared the question
    return await chat.save_answer(
        session,
        result.scope,
        result.question,
        result.prepared,
        content,
        llm.model,
        llm.connection_name,
        result.parent_id,
    )


async def finish_whole(result: TurnResult, llm: LLM) -> uuid.UUID:
    """All of the answer was played: save it whole, and the timing row."""
    async with SessionLocal() as session:
        output_id = await _save(session, result, llm, result.answer)
        await _record(session, result, llm, interrupted=False, stop_ms=None)
    return output_id


async def save_heard(result: TurnResult, played_seconds: float, llm: LLM, stop_ms: int | None) -> uuid.UUID | None:
    """The reader cut in after `played_seconds`: save the part they heard, marked as cut off, and the timing row.
    Nothing heard saves no answer (the timing row is still written)."""
    heard = heard_text(result.chunks, played_seconds)
    async with SessionLocal() as session:
        output_id = await _save(session, result, llm, heard + CUT_OFF) if heard else None
        await _record(session, result, llm, interrupted=True, stop_ms=stop_ms)
    return output_id
