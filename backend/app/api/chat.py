import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LLMDep, SessionDep
from app.core import answer_check_run, answer_provenance, chat, chat_charts, each_paper, hit_chat, notes, queue, skills
from app.core.errors import Conflict, InvalidInput, NotFound
from app.db import SessionLocal
from app.providers.base import LLM, LLMError, LLMUnavailable
from app.schemas.answer_check import AnswerCheckOut, AnswerCheckRequest
from app.schemas.chat import (
    AnswerProvenanceOut,
    ChartAnswerCreated,
    ChatAnswer,
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    HitMetaEvent,
    ReadingEvent,
    ReadingOut,
    ReadingPassage,
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
    if payload.each_paper:
        raise Conflict("each_paper_workspace_only")
    thread = None if payload.parent_id is None else await chat.load_thread(session, paper_id, payload.parent_id)
    skill = await skills.resolve(session, payload.skill_id, "paper")
    return await _prepare(session, chat.Scope(paper_id=paper_id), payload.question, thread, skill)


async def prepare_workspace_answer(
    workspace_id: uuid.UUID, payload: ChatRequest, session: SessionDep
) -> chat.Prepared | None:
    if payload.parent_id is not None:
        raise Conflict("follow_ups_paper_only")  # D62: until workspace follow-ups are measured
    if payload.each_paper:
        return None  # plan_each_paper prepares it
    skill = await skills.resolve(session, payload.skill_id, "workspace")
    return await _prepare(session, chat.Scope(workspace_id=workspace_id), payload.question, skill=skill)


async def plan_each_paper(
    workspace_id: uuid.UUID, payload: ChatRequest, session: SessionDep, llm: LLMDep
) -> each_paper.Plan | None:
    """M8.5: which papers are read and from which passages, before the stream (its errors are ordinary 404/409s)."""
    if not payload.each_paper:
        return None
    skill = await skills.resolve(session, payload.skill_id, "workspace")
    found = await each_paper.plan(session, workspace_id, payload.question, model=llm.model, skill=skill)
    await session.commit()  # the reading can take minutes and must not hold a pooled connection
    return found


PreparedDep = Annotated[chat.Prepared, Depends(prepare_answer)]
WorkspacePreparedDep = Annotated[chat.Prepared | None, Depends(prepare_workspace_answer)]
EachPaperPlanDep = Annotated[each_paper.Plan | None, Depends(plan_each_paper)]


def error_event(message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=ErrorEvent(message=message, retryable=True))


# The route yields ServerSentEvent, so FastAPI can't see the payload models; listing them here puts
# them in OpenAPI components, where openapi-typescript generates their types.
STREAM_RESPONSES = {200: {"model": ReadingEvent | SourcesEvent | TokenEvent | DoneEvent | ErrorEvent}}
NO_TEXT_TO_READ = "None of these papers has text to read"
NOTHING_READ = "The model couldn't read any of these papers"


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


@router.post("/api/workspaces/{workspace_id}/chat", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def ask_workspace(
    workspace_id: uuid.UUID,
    payload: ChatRequest,
    llm: LLMDep,
    prepared: WorkspacePreparedDep,
    plan: EachPaperPlanDep,
) -> AsyncIterable[ServerSentEvent]:
    """Checked before streaming, in parameter order: 404 model_not_found or 409 no_model, then 409
    follow_ups_paper_only, 404, 409 workspace_empty, search_not_set_up or workspace_not_indexed, 422. With
    each_paper (M8.5) the papers are read one by one first, each a reading event."""
    scope = chat.Scope(workspace_id=workspace_id)
    if plan is not None:
        async for event in each_paper_events(scope, payload.question, plan, llm):
            yield event
        return
    async for event in answer_events(scope, payload.question, prepared, llm):
        yield event


def to_reading(reading: each_paper.Reading) -> ReadingOut:
    passages = [ReadingPassage(chunk_id=c.id, page=c.page, section=c.section, text=c.text) for c in reading.cited]
    return ReadingOut(
        output_id=reading.output_id, paper_id=reading.paper_id, label=reading.label, status=reading.status,
        answer=reading.answer, cited=passages, low_confidence=reading.low_confidence,
    )


def to_answer(
    answer: chat.Answer, checked: set[uuid.UUID] = frozenset(), readings: dict[uuid.UUID, each_paper.Reading] = {}
) -> ChatAnswer:
    output = answer.output
    return ChatAnswer(
        id=output.id,
        has_check=output.id in checked,
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
        readings=[to_reading(readings[r.id]) for r in answer.readings if r.id in readings],
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
    return await _with_checks(session, await chat.list_answers(session, paper_id))


@router.get("/api/workspaces/{workspace_id}/chat")
async def workspace_history(workspace_id: uuid.UUID, session: SessionDep) -> list[ChatAnswer]:
    return await _with_checks(session, await chat.list_answers(session, chat.Scope(workspace_id=workspace_id)))


async def _with_checks(session: AsyncSession, answers: list[chat.Answer]) -> list[ChatAnswer]:
    checked = await answer_check_run.checked_answers(session, [answer.output.id for answer in answers])
    readings = await each_paper.views_of(session, [r for answer in answers for r in answer.readings])
    return [to_answer(answer, checked, readings) for answer in answers]


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


def to_check(check) -> AnswerCheckOut:
    result = check.check_result
    return AnswerCheckOut(
        id=check.id, state=result["state"], model=check.model, connection_name=check.connection_name,
        created_at=check.created_at, summary=check.content, limit_hit=result["limit_hit"],
        sentences=result["sentences"],
    )


@router.post("/api/chat/answers/{output_id}/check", status_code=202)
async def start_answer_check(
    output_id: uuid.UUID, session: SessionDep, payload: AnswerCheckRequest | None = None
) -> AnswerCheckOut:
    """Checks each cited sentence of a saved answer against the passages it cites (M34), in a background job; poll
    GET. A check still running is returned as it is. 404 answer_not_found; 409 answer_not_checkable (saved before
    PaperLab kept its passages) or remote_model_needs_confirm (send confirm_remote)."""
    payload = payload or AnswerCheckRequest()
    check, new = await answer_check_run.start_check(
        session, output_id, model_id=payload.model_id, confirmed=payload.confirm_remote
    )
    if new:
        try:
            await queue.enqueue(answer_check_run.JOB, str(check.id))
        except Exception as exc:  # Redis down: never leave a "running" check that no job will finish
            logger.exception("answer check %s could not be queued", check.id)
            await answer_check_run.mark_failed(session, check.id)
            raise Conflict("check_not_queued") from exc
    return to_check(check)


@router.get("/api/chat/answers/{output_id}/check")
async def get_answer_check(output_id: uuid.UUID, session: SessionDep) -> AnswerCheckOut:
    """The answer's newest check. 404 check_not_found."""
    check = await answer_check_run.latest_check(session, output_id)
    if check is None:
        raise NotFound("check_not_found")
    return to_check(check)


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
