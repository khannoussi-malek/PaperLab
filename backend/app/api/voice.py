import asyncio
import logging
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.api.deps import SpeechDep, TransportDep
from app.config import LOCAL_HOSTS
from app.core import chat, llm_connections
from app.core.errors import DomainError, error_code
from app.core.voice_turn import (
    CANNOT_ANSWER,
    UNEXPECTED,
    TurnResult,
    finish_whole,
    mark_false_interrupt,
    run_turn,
    save_heard,
)
from app.db import SessionLocal
from app.providers.base import LLM, Speech, SpeechUnavailable
from app.providers.llm import build_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_UTTERANCE_BYTES = 16000 * 4 * 60  # a minute of 16 kHz float32
BAD_UTTERANCE = "That recording couldn't be used. Try asking again."
SAVE_FAILED = "That answer couldn't be saved."
BAD_MESSAGE = "PaperLab didn't understand that message from the page. Reload the page and try again."
# Words for the model refusals, the same as typed chat's panel (frontend/src/features/chat/refusals.ts).
MODEL_REFUSALS = {
    "model_not_found": ("The model you picked was removed. Ask again to use the default model.", True),
    "no_model": ("No model is set up for chat yet.", False),
}
CLOSE_BAD_MESSAGE = 4400
CLOSE_FOREIGN_ORIGIN = 4403


class VoiceStatus(BaseModel):
    ready: bool
    detail: str | None = None


@router.get("/status")
async def status(speech: SpeechDep) -> VoiceStatus:
    try:
        ready = await speech.health()
    except SpeechUnavailable as e:
        return VoiceStatus(ready=False, detail=str(e))
    return VoiceStatus(ready=ready, detail=None if ready else "The voice program is still loading its models.")


class Start(BaseModel):
    type: Literal["start"]
    scope: Literal["paper", "workspace"]
    id: uuid.UUID
    model_id: uuid.UUID | None = None


class Interrupt(BaseModel):
    type: Literal["interrupt"]
    played_seconds: float = Field(ge=0, allow_inf_nan=False)
    stop_ms: int | None = Field(default=None, ge=0)


class Metrics(BaseModel):
    type: Literal["metrics"]
    turn: int
    wait_ms: int = Field(ge=0)
    output_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)


class Finished(BaseModel):
    type: Literal["finished"]


_parse_message = TypeAdapter(Annotated[Start | Interrupt | Metrics | Finished, Field(discriminator="type")])


async def load_llm(model_id: uuid.UUID | None, transport) -> LLM:
    """The adapter for this question's model, or the default's, from a short session closed before the answer runs
    (a socket can't hold a request-scoped one): a model removed mid-session is an error message, not a dropped one."""
    async with SessionLocal() as session:
        connection, model = await llm_connections.resolve(session, model_id)
    return build_llm(connection, model.name, transport=transport)


_FAILED = object()  # what _keep_on_failure returns when a save raised


@dataclass
class _Turn:
    number: int  # 1, 2, ...: what the page's `metrics` message names
    result: TurnResult
    task: asyncio.Task | None = None
    llm: LLM | None = None  # None until the model resolved
    streamed: bool = False  # all of the answer was sent


class _Connection:
    """One page's voice session. Messages are handled one at a time; a turn runs as a task, so `interrupt` can arrive
    while it runs."""

    def __init__(self, ws: WebSocket, speech: Speech, transport, start: Start):
        self.ws = ws
        self.speech = speech
        self.transport = transport
        self.scope = chat.Scope(
            paper_id=start.id if start.scope == "paper" else None,
            workspace_id=start.id if start.scope == "workspace" else None,
        )
        self.model_id = start.model_id
        self.turns = 0
        self.current: _Turn | None = None  # the latest turn that is not yet saved or dropped
        self.last_output_id: uuid.UUID | None = None  # the parent of the next paper turn
        self.interrupted_row: uuid.UUID | None = None  # the last cut-in's timing row, until the next turn is heard

    async def send(self, message: dict | bytes) -> None:
        if isinstance(message, bytes):
            await self.ws.send_bytes(message)
        else:
            await self.ws.send_json(message)

    async def error(self, message: str, retryable: bool = False) -> None:
        await self.send({"type": "error", "message": message, "retryable": retryable})

    async def stop(self) -> None:
        """Cancels the running turn and waits until it has ended, so what it filled is final."""
        task = self.current.task if self.current else None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.wait([task])  # never raises the turn's own failure or its cancel

    async def handle(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            return await self.utterance(raw)
        try:
            message = _parse_message.validate_json(raw)
        except ValidationError:
            return await self.error(BAD_MESSAGE)
        match message:
            case Interrupt():
                await self.interrupt(message)
            case Metrics():
                self.metrics(message)
            case Finished():
                await self.finished()
            case _:  # a second start
                await self.error(BAD_MESSAGE)

    async def utterance(self, samples: bytes) -> None:
        if not samples or len(samples) % 4 or len(samples) > MAX_UTTERANCE_BYTES:
            return await self.error(BAD_UTTERANCE)
        await self.stop()  # a new question while an answer plays: the old turn saves nothing
        self.turns += 1
        parent = self.last_output_id if self.scope.paper_id is not None else None  # D62: workspaces have no follow-ups
        result = TurnResult(scope=self.scope, cold=self.turns == 1, number=self.turns, parent_id=parent)
        turn = _Turn(self.turns, result)
        turn.task = asyncio.create_task(self._run(turn, samples))
        self.current = turn

    async def _run(self, turn: _Turn, samples: bytes) -> None:
        try:
            try:
                turn.llm = await load_llm(self.model_id, self.transport)
            except DomainError as e:
                return await self.error(*MODEL_REFUSALS.get(error_code(e), (CANNOT_ANSWER, False)))
            await run_turn(turn.result, samples, turn.llm, self.speech, self.send)
            turn.streamed = not turn.result.ended
            await self._judge_last_interrupt(turn.result)
        except WebSocketDisconnect:
            logger.debug("the page left during voice turn %s", turn.number)  # an ordinary end, not a failure
        except Exception:  # something unforeseen: the page is told if it can be
            logger.exception("voice turn %s stopped unexpectedly", turn.number)
            try:
                await self.error(UNEXPECTED, retryable=True)
            except Exception:
                logger.info("could not tell the page, which has probably gone")

    async def _judge_last_interrupt(self, result: TurnResult) -> None:
        """No words after a cut-in: noise or echo probably caused it.
        ponytail: only an estimate; echo that transcribes to words looks like a real question and is missed."""
        if self.interrupted_row is None or result.ended:
            return
        row, self.interrupted_row = self.interrupted_row, None
        if not result.question:
            await mark_false_interrupt(row)

    async def interrupt(self, message: Interrupt) -> None:
        turn = self.current
        if turn is None:
            return
        await self.stop()  # also while the model is still resolving: the turn ends before it starts
        if turn.llm is None or turn.result.ended:  # nothing was streamed, or the turn already failed
            self.current = None
            return
        output_id = await self._keep_on_failure(
            save_heard(turn.result, message.played_seconds, turn.llm, message.stop_ms)
        )
        if output_id is _FAILED:
            return
        self.current = None
        self.interrupted_row = turn.result.row_id
        await self._saved(output_id)

    async def finished(self) -> None:
        turn = self.current
        if turn is None or turn.llm is None or not turn.streamed:
            return
        output_id = await self._keep_on_failure(finish_whole(turn.result, turn.llm))
        if output_id is _FAILED:
            return
        self.current = None
        await self._saved(output_id)

    async def _keep_on_failure(self, saving: Awaitable[uuid.UUID | None]) -> uuid.UUID | None | object:
        """The save's result; or _FAILED, after telling the page, when the database failed. The turn stays current, so
        the page's next `finished` or `interrupt` tries again."""
        try:
            return await saving
        except Exception:
            logger.exception("saving a voice answer failed")
            await self.error(SAVE_FAILED, retryable=True)
            return _FAILED

    def metrics(self, message: Metrics) -> None:
        turn = self.current
        if turn is None or turn.number != message.turn or turn.result.ended:
            return
        turn.result.timing.update(wait_ms=message.wait_ms, output_ms=message.output_ms, total_ms=message.total_ms)

    async def _saved(self, output_id: uuid.UUID | None) -> None:
        if output_id is None:
            return
        self.last_output_id = output_id
        await self.send({"type": "saved", "output_id": str(output_id)})


@router.websocket("/ws")
async def voice_ws(ws: WebSocket, speech: SpeechDep, transport: TransportDep) -> None:
    # The HTTP middlewares don't see WebSocket origins. A missing header is allowed, as same_origin_writes allows it.
    origin = ws.headers.get("origin")
    if origin is not None and urlparse(origin).hostname not in LOCAL_HOSTS:
        await ws.close(CLOSE_FOREIGN_ORIGIN)
        return
    await ws.accept()
    first = await ws.receive()
    try:
        start = _parse_message.validate_json(first["text"]) if first.get("text") else None
    except ValidationError:
        start = None
    if not isinstance(start, Start):
        if first["type"] != "websocket.disconnect":
            await ws.close(CLOSE_BAD_MESSAGE)
        return
    connection = _Connection(ws, speech, transport, start)
    try:
        while (message := await ws.receive())["type"] != "websocket.disconnect":
            await connection.handle(message["bytes"] if message.get("bytes") is not None else message["text"])
    except WebSocketDisconnect:  # a send found the page gone
        pass
    finally:
        # ponytail: a dropped connection saves nothing; the server can't know how much of the answer was heard.
        await connection.stop()
