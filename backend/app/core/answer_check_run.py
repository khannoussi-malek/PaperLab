"""Starting, running and reading an answer check (M34). A check is one llm_outputs row (kind answer_check, parent_id
the answer) whose check_result a background job fills sentence by sentence, committing after each so a poll sees it.

check_result: {state: running|done|failed, model_id, limit_hit, sentences: [{index, text, labels, state:
pending|done|not_cited|not_kept|not_checked, verdict, reason, quote, quote_label, confidence, shortened}]}.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections
from app.core.answer_check import (
    ANSWER_CHECK_PROMPT_VERSION,
    MAX_CHECK_SENTENCES,
    OUTPUT_KIND,
    CheckPassage,
    check_sentence,
)
from app.core.answer_check_text import answer_sentences
from app.core.answer_provenance import MAX_SNAPSHOT_CHARS
from app.core.errors import Conflict, NotFound
from app.models import Chunk, LLMOutput, Paper
from app.providers.llm import build_llm

JOB = "check_answer"
ANSWER_CHECK_JOB_TIMEOUT = 1800  # seconds: 20 sentences at up to ~90 s each on a slow local model
# A check still "running" this long after it was started has lost its job (killed, timed out, never queued): it is
# read as failed. The margin covers a job that waited in the queue before its own timeout started.
STALE_AFTER = ANSWER_CHECK_JOB_TIMEOUT + 600

# The summary's words, in its order. Verdicts come from done sentences, the rest from the sentence state.
_SUMMARY = [
    ("supported", "supported"),
    ("partially_supported", "partly supported"),
    ("not_supported", "not supported"),
    ("not_addressed", "not addressed"),
    ("couldnt_check", "couldn't check"),
    ("not_cited", "not cited"),
    ("not_kept", "passage not kept"),
    ("not_checked", "not checked"),
]


def summary_line(sentences: list[dict]) -> str:
    counts = Counter(s["verdict"] if s["state"] == "done" else s["state"] for s in sentences)
    return " · ".join(f"{counts[key]} {words}" for key, words in _SUMMARY if counts[key])


def _blank(index: int, text: str, labels: tuple[str, ...], state: str) -> dict:
    return {"index": index, "text": text, "labels": list(labels), "state": state, "verdict": None, "reason": None,
            "quote": None, "quote_label": None, "confidence": None, "shortened": False}


def _initial(content: str) -> tuple[list[dict], bool]:
    sentences, cited = [], 0
    for s in answer_sentences(content):
        if not s.labels:
            state = "not_cited"
        else:
            cited += 1
            state = "pending" if cited <= MAX_CHECK_SENTENCES else "not_checked"
        sentences.append(_blank(s.index, s.text, s.labels, state))
    return sentences, cited > MAX_CHECK_SENTENCES


async def latest_check(session: AsyncSession, output_id: uuid.UUID) -> LLMOutput | None:
    """The answer's newest check; one left "running" past STALE_AFTER is saved as failed first, so the reader can
    check again instead of watching a spinner forever."""
    query = (
        select(LLMOutput)
        .where(LLMOutput.parent_id == output_id, LLMOutput.kind == OUTPUT_KIND)
        .order_by(LLMOutput.created_at.desc(), LLMOutput.id)
        .limit(1)
    )
    check = await session.scalar(query)
    if check is not None and _stale(check):
        await _save(session, check, {**check.check_result, "state": "failed"})
    return check


def _stale(check: LLMOutput) -> bool:
    running = (check.check_result or {}).get("state") == "running"
    return running and check.created_at <= datetime.now(UTC) - timedelta(seconds=STALE_AFTER)


def _running(check: LLMOutput | None) -> bool:
    return check is not None and (check.check_result or {}).get("state") == "running"  # latest_check failed stale ones


async def start_check(
    session: AsyncSession, output_id: uuid.UUID, *, model_id: uuid.UUID | None, confirmed: bool
) -> tuple[LLMOutput, bool]:
    """The check to show and whether it is new (its job still has to be queued). NotFound answer_not_found unless a
    chat answer has that id; Conflict answer_not_checkable for an answer saved before M33 kept its passages;
    remote_model_needs_confirm (and the model errors) from llm_connections.refuse_unconfirmed_remote."""
    answer = await session.get(LLMOutput, output_id)
    if answer is None or answer.kind != "chat":
        raise NotFound("answer_not_found")
    if answer.source_snapshot is None:
        raise Conflict("answer_not_checkable")
    current = await latest_check(session, output_id)
    if _running(current):
        return current, False
    connection, model = await llm_connections.refuse_unconfirmed_remote(session, confirmed, model_id)
    sentences, limit_hit = _initial(answer.content)
    check = LLMOutput(
        kind=OUTPUT_KIND,
        parent_id=answer.id,
        paper_id=answer.paper_id,
        workspace_id=answer.workspace_id,
        question=None,
        content=summary_line(sentences),
        source_chunks=list(answer.cited_chunks),
        cited_chunks=list(answer.cited_chunks),
        model=model.name,
        connection_name=connection.label,
        prompt_version=ANSWER_CHECK_PROMPT_VERSION,
        check_result={"state": "running", "model_id": str(model.id), "limit_hit": limit_hit, "sentences": sentences},
    )
    session.add(check)
    await session.commit()
    return check, True


async def _passages(session: AsyncSession, answer: LLMOutput, labels: list[str]) -> list[CheckPassage] | None:
    """The sentence's passages: the live chunk's whole text while it exists, else the snapshot's copy. None when a
    label has no snapshot entry (a passage M33 didn't keep)."""
    by_label = {entry["label"]: entry for entry in answer.source_snapshot or []}
    entries = [by_label.get(label) for label in labels]
    if any(entry is None for entry in entries):
        return None
    titles = dict((await session.execute(
        select(Paper.id, Paper.title).where(Paper.id.in_({uuid.UUID(e["paper_id"]) for e in entries}))
    )).all())
    passages = []
    for label, entry in zip(labels, entries, strict=True):
        number = int(label[1:])
        chunk_id = answer.source_chunks[number - 1] if number <= len(answer.source_chunks) else None
        chunk = await session.get(Chunk, chunk_id) if chunk_id is not None else None
        text = chunk.text if chunk is not None else entry["text"]
        shortened = chunk is None and len(entry["text"]) >= MAX_SNAPSHOT_CHARS
        page = None if entry.get("from_abstract") else entry.get("page")
        title = titles.get(uuid.UUID(entry["paper_id"]), "Untitled paper")
        passages.append(CheckPassage(label, title, page, entry.get("section"), text, shortened))
    return passages


async def _save(session: AsyncSession, check: LLMOutput, result: dict) -> None:
    check.check_result = result  # a new dict each time: JSONB changes are only seen on reassignment
    check.content = summary_line(result["sentences"])
    await session.commit()


async def run_check(session: AsyncSession, check_id: uuid.UUID, llm=None) -> None:
    check = await session.get(LLMOutput, check_id)
    if check is None or check.kind != OUTPUT_KIND:
        raise NotFound("check_not_found")
    answer = await session.get(LLMOutput, check.parent_id) if check.parent_id else None
    if answer is None:
        raise NotFound("answer_not_found")
    if llm is None:
        connection, model = await llm_connections.resolve(session, uuid.UUID(check.check_result["model_id"]))
        llm = build_llm(connection, model.name)
    result = check.check_result
    for position, sentence in enumerate(result["sentences"]):
        if sentence["state"] != "pending":
            continue
        passages = await _passages(session, answer, sentence["labels"])
        if passages is None:
            filled = {**sentence, "state": "not_kept"}
        else:
            verdict = await check_sentence(llm, sentence["text"], passages)
            filled = {**sentence, "state": "done", "verdict": verdict.verdict, "reason": verdict.reason,
                      "quote": verdict.quote, "quote_label": verdict.quote_label, "confidence": verdict.confidence,
                      "shortened": any(p.shortened for p in passages)}
        sentences = [*result["sentences"][:position], filled, *result["sentences"][position + 1 :]]
        result = {**result, "sentences": sentences}
        await _save(session, check, result)
    await _save(session, check, {**result, "state": "done"})


async def mark_failed(session: AsyncSession, check_id: uuid.UUID) -> None:
    check = await session.get(LLMOutput, check_id)
    if check is not None and check.kind == OUTPUT_KIND:
        await _save(session, check, {**check.check_result, "state": "failed"})
