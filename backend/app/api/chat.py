import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LLMDep, SessionDep
from app.core import answer_provenance, chat, chat_charts, hit_chat, notes, skills
from app.core.errors import Conflict, InvalidInput
from app.db import SessionLocal
from app.providers.base import LLM, LLMError, LLMUnavailable
from app.schemas.chat import (
    AnswerProvenanceOut,
    ChartAnswerCreated,
    ChatAnswer,
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    HitMetaEvent,
    SavedNoteOut,
    SaveSuggestion,
    SourcesEvent,
    TokenEvent,
    to_notes,
    to_provenance,
    to_sources,
)
from app.schemas.notes import NoteOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def _prepare(
    session: AsyncSession,
    scope: chat.Scope,
    question: str,
    thread: chat.Thread | None = None,
    skill: skills.SkillView | None = None,
) -> chat.Prepared:
    """Runs before the stream starts: once an SSE response has begun, an exception only drops the connection."""
    prepared = await chat.prepare(session, scope, question, thread=thread, skill=skill)
    # End the transaction now. The LLM stream can take minutes and must not hold a pooled connection.
    await session.commit()
    return prepared


async def prepare_answer(paper_id: uuid.UUID, payload: ChatRequest, session: SessionDep) -> chat.Prepared:
    thread = None if payload.parent_id is None else await chat.load_thread(session, paper_id, payload.parent_id)
    skill = await skills.resolve(session, payload.skill_id, "paper")
    return await _prepare(session, chat.Scope(paper_id=paper_id), payload.question, thread, skill)


async def prepare_workspace_answer(workspace_id: uuid.UUID, payload: ChatRequest, session: SessionDep) -> chat.Prepared:
    if payload.parent_id is not None:
        raise Conflict("follow_ups_paper_only")  # D62: until workspace follow-ups are measured
    skill = await skills.resolve(session, payload.skill_id, "workspace")
    return await _prepare(session, chat.Scope(workspace_id=workspace_id), payload.question, skill=skill)


PreparedDep = Annotated[chat.Prepared, Depends(prepare_answer)]
WorkspacePreparedDep = Annotated[chat.Prepared, Depends(prepare_workspace_answer)]


def error_event(message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=ErrorEvent(message=message, retryable=True))


# The route yields ServerSentEvent, so FastAPI can't see the payload models; listing them here puts
# them in OpenAPI components, where openapi-typescript generates their types.
STREAM_RESPONSES = {200: {"model": SourcesEvent | TokenEvent | DoneEvent | ErrorEvent}}


Save = Callable[[AsyncSession, str], Awaitable[uuid.UUID]]


async def stream_output(
    prepared: chat.Prepared, llm: LLM, save: Save, noun: str, log_as: str, log_for: object
) -> AsyncIterable[ServerSentEvent]:
    """Events: sources, token (repeated), then done. error replaces done, and then nothing is saved.

    `save` stores the finished text in a fresh session and returns its id; `noun` names the output in the error texts
    ("answer", "brief") and `log_as` in the logs ("chat answer", "brief"), because chat's tests assert its log text;
    `log_for` names what a failed save was for (chat's scope, a brief's paper and lens).
    Shared by chat and M16's briefs (and M22's check, D175)."""
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

    cited = [f"C{i}" for i in chat.parse_citations(content, len(prepared.sources))]
    cited += [f"N{i}" for i in chat.parse_citations(content, len(prepared.notes), "N")]
    done = DoneEvent(
        output_id=output_id,
        model=llm.model,
        connection_name=llm.connection_name,
        prompt_version=prepared.prompt_version,
        cited=cited,
        skill_label=prepared.skill_label,
        lens=prepared.lens,
    )
    yield ServerSentEvent(event="done", data=done)


async def answer_events(
    scope: chat.Scope, question: str, prepared: chat.Prepared, llm: LLM, parent_id: uuid.UUID | None = None
) -> AsyncIterable[ServerSentEvent]:
    """A chat answer's stream (stream_output), saved as a chat answer."""

    async def save(session: AsyncSession, content: str) -> uuid.UUID:
        return await chat.save_answer(
            session, scope, question, prepared, content, llm.model, llm.connection_name, parent_id
        )

    async for event in stream_output(prepared, llm, save, "answer", "chat answer", scope):
        yield event


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
        sources=to_sources(answer.sources, answer.replaced),
        notes=to_notes(answer.notes),
        notes_used=output.notes_used,
        notes_total=output.notes_total,
        parent_id=output.parent_id,
        saved_notes=[SavedNoteOut(index=s.index, note_id=s.note_id, paper_ids=s.paper_ids) for s in answer.saved_notes],
        skill_label=output.skill_label,
        lens=output.lens,
        chart_spec=output.chart_spec,
    )


@router.post("/api/papers/{paper_id}/chat/chart", status_code=201)
async def paper_chart(
    paper_id: uuid.UUID, payload: ChatRequest, session: SessionDep, llm: LLMDep
) -> ChartAnswerCreated:
    """A chart of the paper's captured data, saved as a chat answer (M14). 422 says in words why nothing was drawn."""
    scope = chat.Scope(paper_id=paper_id)
    return ChartAnswerCreated(output_id=await chat_charts.ask_chart(session, scope, payload.question, llm))


@router.post("/api/workspaces/{workspace_id}/chat/chart", status_code=201)
async def workspace_chart(
    workspace_id: uuid.UUID, payload: ChatRequest, session: SessionDep, llm: LLMDep
) -> ChartAnswerCreated:
    scope = chat.Scope(workspace_id=workspace_id)
    return ChartAnswerCreated(output_id=await chat_charts.ask_chart(session, scope, payload.question, llm))


@router.get("/api/papers/{paper_id}/chat")
async def history(paper_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return [to_answer(answer) for answer in await chat.list_answers(session, paper_id)]


@router.get("/api/workspaces/{workspace_id}/chat")
async def workspace_history(workspace_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return [to_answer(answer) for answer in await chat.list_answers(session, chat.Scope(workspace_id=workspace_id))]


@router.get("/api/llm-outputs/{output_id}/provenance")
async def output_provenance(output_id: uuid.UUID, session: SessionDep) -> AnswerProvenanceOut:
    """How an answer or a brief was made, and where each cited passage stands now (M33). 404 answer_not_found."""
    return to_provenance(await answer_provenance.provenance(session, output_id))


@router.post("/api/chat/answers/{output_id}/notes", status_code=201)
async def save_suggestion(output_id: uuid.UUID, payload: SaveSuggestion, session: SessionDep) -> NoteOut:
    """Saves the answer's :::note block `index` as an AI note, read from the stored answer (D94). 404 answer_not_found;
    409 already_saved (the history's saved_notes names the note); 422 no_such_block, empty_body, or a cited passage a
    re-ingest replaced."""
    return await notes.save_suggestion(session, output_id, payload.index)


HIT_STREAM_RESPONSES = {200: {"model": HitMetaEvent | SourcesEvent | TokenEvent | DoneEvent | ErrorEvent}}
HIT_CHAT = "/api/workspaces/{workspace_id}/search/hits/{hit_id}/chat"


@dataclass(frozen=True)
class HitPrepared:
    source: str
    paper_id: uuid.UUID | None  # read before _prepare commits, which expires the ORM objects
    prepared: chat.Prepared
    parent_id: uuid.UUID | None  # the answer a follow-up follows; None when it starts a thread


async def prepare_hit_answer(
    workspace_id: uuid.UUID, hit_id: uuid.UUID, payload: ChatRequest, session: SessionDep
) -> HitPrepared:
    if payload.skill_id is not None:  # hit chat keeps its own prompt; no skill runs here (M17 §1)
        raise InvalidInput("skill_not_here")
    context = await hit_chat.load(session, workspace_id, hit_id)
    if context.source == "abstract":
        prepared = hit_chat.prepare_abstract(context, payload.question, payload.parent_id)
        await session.commit()  # the stream can take minutes; don't hold a pooled connection
        return HitPrepared("abstract", None, prepared, payload.parent_id)
    paper_id = context.paper.id
    # An abstract answer's id (the hit gained full text mid-thread) isn't a paper answer: start a new thread.
    parent_id = payload.parent_id
    if parent_id is not None and any(a.id == parent_id for a in hit_chat.HISTORY.get(hit_id, [])):
        parent_id = None
    thread = None if parent_id is None else await chat.load_thread(session, paper_id, parent_id)
    prepared = await _prepare(session, chat.Scope(paper_id=paper_id), payload.question, thread)
    return HitPrepared("full_text", paper_id, prepared, parent_id)


HitPreparedDep = Annotated[HitPrepared, Depends(prepare_hit_answer)]


@router.post(HIT_CHAT, response_class=EventSourceResponse, responses=HIT_STREAM_RESPONSES)
async def ask_hit(
    hit_id: uuid.UUID, payload: ChatRequest, llm: LLMDep, ready: HitPreparedDep
) -> AsyncIterable[ServerSentEvent]:
    """Checked before streaming, in parameter order: 404/409 for the model, then 404 for a missing or foreign hit, then
    paper chat's checks when the hit has full text. The first event is `meta`, with source "abstract" or "full_text"."""
    yield ServerSentEvent(event="meta", data=HitMetaEvent(source=ready.source))
    if ready.paper_id is not None:
        scope = chat.Scope(paper_id=ready.paper_id)
        events = answer_events(scope, payload.question, ready.prepared, llm, ready.parent_id)
    else:

        async def save(_: AsyncSession, content: str) -> uuid.UUID:
            return hit_chat.remember(hit_id, payload.question, content, llm.model, llm.connection_name, ready.parent_id)

        events = stream_output(ready.prepared, llm, save, "answer", "hit chat answer", hit_id)
    async for event in events:
        yield event


@router.get(HIT_CHAT)
async def hit_history(workspace_id: uuid.UUID, hit_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    """Abstract-only answers (kept in memory, lost on restart) then the paper's stored answers when it has full text."""
    context = await hit_chat.load(session, workspace_id, hit_id)
    answers = list(hit_chat.HISTORY.get(hit_id, []))
    if context.source == "full_text":
        answers += [to_answer(a) for a in await chat.list_answers(session, context.paper.id)]
    return sorted(answers, key=lambda a: a.created_at)
