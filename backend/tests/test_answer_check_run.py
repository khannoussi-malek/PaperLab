import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update
from test_chat import chunks_of, make_paper

from app.core.chat import answer_check_run, claims
from app.core.chat.answer_check_run import (
    ANSWER_CHECK_JOB_TIMEOUT,
    latest_check,
    run_check,
    start_check,
    summary_line,
)
from app.core.chat.answer_provenance import MAX_SNAPSHOT_CHARS
from app.domain.errors import Conflict, NotFound
from app.models import Chunk, LLMConnection, LLMModel, LLMOutput
from app.providers.llm_fake import FakeLLM
from app.workers import answer_check as worker

pytestmark = pytest.mark.anyio

LONG = "The big model reaches 28.4 BLEU on English-to-German. " + "Filler words about training. " * 90 + "Tail fact."


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(claims, "sleep", instant)


async def make_answer(session, content: str, texts: list[str], *, snapshot=True, **fields) -> tuple[LLMOutput, list]:
    paper = await make_paper(session, texts)
    chunks = await chunks_of(session, paper.id)
    entries = [
        {"label": f"C{i}", "paper_id": str(paper.id), "page": c.page, "section": c.section_title,
         "text": c.text[:MAX_SNAPSHOT_CHARS], "from_abstract": False}
        for i, c in enumerate(chunks, start=1)
    ]
    answer = LLMOutput(
        paper_id=paper.id, kind="chat", question="why?", content=content, model="m", prompt_version=7,
        source_chunks=[c.id for c in chunks], cited_chunks=[c.id for c in chunks],
        source_snapshot=entries if snapshot else None, **fields,
    )
    session.add(answer)
    await session.commit()
    return answer, chunks


async def test_start_check_creates_running_row(session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1]. Ask a colleague.", ["28.4 BLEU here."])

    check, new = await start_check(session, answer.id, model_id=None, confirmed=False)

    assert new is True
    assert (check.kind, check.parent_id, check.question) == ("answer_check", answer.id, None)
    assert check.paper_id == answer.paper_id
    assert check.model == "qwen3:8b"
    result = check.check_result
    assert result["state"] == "running" and result["limit_hit"] is False
    assert [(s["text"], s["labels"], s["state"]) for s in result["sentences"]] == [
        ("It reaches 28.4 BLEU.", ["C1"], "pending"),
        ("Ask a colleague.", [], "not_cited"),
    ]


async def test_second_start_returns_running_check(session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["28.4 BLEU here."])
    first, _ = await start_check(session, answer.id, model_id=None, confirmed=False)

    again, new = await start_check(session, answer.id, model_id=None, confirmed=False)

    assert (again.id, new) == (first.id, False)


async def test_stale_running_check_is_replaced(session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["28.4 BLEU here."])
    first, _ = await start_check(session, answer.id, model_id=None, confirmed=False)
    old = datetime.now(UTC) - timedelta(seconds=answer_check_run.STALE_AFTER + 60)
    await session.execute(update(LLMOutput).where(LLMOutput.id == first.id).values(created_at=old))
    await session.commit()

    again, new = await start_check(session, answer.id, model_id=None, confirmed=False)

    assert new is True and again.id != first.id


async def test_refuses_answer_without_snapshot(session, local_default_model):
    answer, _ = await make_answer(session, "Old [C1].", ["text"], snapshot=False)
    with pytest.raises(Conflict) as err:
        await start_check(session, answer.id, model_id=None, confirmed=False)
    assert str(err.value) == "answer_not_checkable"


async def test_refuses_non_chat_output(session, local_default_model):
    answer, _ = await make_answer(session, "Brief [C1].", ["text"])
    await session.execute(update(LLMOutput).where(LLMOutput.id == answer.id).values(kind="brief"))
    with pytest.raises(NotFound) as err:
        await start_check(session, answer.id, model_id=None, confirmed=False)
    assert str(err.value) == "answer_not_found"
    with pytest.raises(NotFound):
        await start_check(session, uuid.uuid4(), model_id=None, confirmed=False)


async def test_cloud_model_needs_confirm(session):
    await session.execute(update(LLMModel).values(is_default=False))
    cloud = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(cloud)
    await session.flush()
    session.add(LLMModel(connection_id=cloud.id, name="big", is_default=True))
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["28.4 BLEU here."])

    with pytest.raises(Conflict) as err:
        await start_check(session, answer.id, model_id=None, confirmed=False)
    assert str(err.value) == "remote_model_needs_confirm"
    check, new = await start_check(session, answer.id, model_id=None, confirmed=True)
    assert new and check.connection_name == "Cloud"


async def test_limit(session, local_default_model):
    content = " ".join(f"Fact number {i} holds [C1]." for i in range(25))
    answer, _ = await make_answer(session, content, ["facts"])

    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)

    states = [s["state"] for s in check.check_result["sentences"]]
    assert states == ["pending"] * 20 + ["not_checked"] * 5
    assert check.check_result["limit_hit"] is True


async def test_run_check_fills_every_sentence(session, local_default_model):
    content = "It reaches 28.4 BLEU [C1]. Ask a colleague."
    answer, _ = await make_answer(session, content, ["It reaches 28.4 BLEU here."])
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)

    await run_check(session, check.id, llm=FakeLLM())

    done = await latest_check(session, answer.id)
    assert done.id == check.id and done.check_result["state"] == "done"
    first = done.check_result["sentences"][0]
    assert (first["state"], first["verdict"], first["quote_label"]) == ("done", "supported", "C1")
    assert first["shortened"] is False
    assert done.content == summary_line(done.check_result["sentences"]) == "1 supported · 1 not cited"


async def test_uses_live_chunk_text_when_present(session, local_default_model):
    answer, _ = await make_answer(session, "There is a tail fact [C1].", [LONG])
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)
    llm = FakeLLM()

    await run_check(session, check.id, llm=llm)

    assert "Tail fact." in llm.calls[0][1]
    assert (await latest_check(session, answer.id)).check_result["sentences"][0]["shortened"] is False


async def test_falls_back_to_snapshot_after_reingest(session, local_default_model):
    answer, chunks = await make_answer(session, "There is a tail fact [C1].", [LONG])
    await session.execute(delete(Chunk).where(Chunk.id == chunks[0].id))
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)
    llm = FakeLLM()

    await run_check(session, check.id, llm=llm)

    assert "Tail fact." not in llm.calls[0][1]
    assert (await latest_check(session, answer.id)).check_result["sentences"][0]["shortened"] is True


async def test_label_missing_from_snapshot_is_not_kept(session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C2].", ["28.4 BLEU here."])
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)
    llm = FakeLLM()

    await run_check(session, check.id, llm=llm)

    assert llm.calls == []
    assert (await latest_check(session, answer.id)).check_result["sentences"][0]["state"] == "not_kept"


async def test_worker_marks_failed_on_crash(session, local_default_model, monkeypatch):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["28.4 BLEU here."])
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)

    @asynccontextmanager
    async def shared():
        yield session

    async def boom(*_args, **_kwargs):
        raise RuntimeError("worker died")

    monkeypatch.setattr(worker, "SessionLocal", shared)
    monkeypatch.setattr(answer_check_run, "run_check", boom)
    await worker.check_answer({}, str(check.id))

    assert (await latest_check(session, answer.id)).check_result["state"] == "failed"


def test_summary_line_order_and_zeros():
    sentences = [
        {"state": "not_cited", "verdict": None},
        {"state": "done", "verdict": "not_supported"},
        {"state": "done", "verdict": "supported"},
        {"state": "done", "verdict": "supported"},
        {"state": "done", "verdict": "partially_supported"},
        {"state": "done", "verdict": "couldnt_check"},
        {"state": "not_checked", "verdict": None},
    ]
    assert summary_line(sentences) == (
        "2 supported · 1 partly supported · 1 not supported · 1 couldn't check · 1 not cited · 1 not checked"
    )
    assert summary_line([]) == ""


async def test_a_running_check_past_its_time_reads_as_failed(session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["28.4 BLEU here."])
    check, _ = await start_check(session, answer.id, model_id=None, confirmed=False)
    old = datetime.now(UTC) - timedelta(seconds=answer_check_run.STALE_AFTER + 60)
    await session.execute(update(LLMOutput).where(LLMOutput.id == check.id).values(created_at=old))
    await session.commit()
    check_id, answer_id = check.id, answer.id
    session.expire_all()  # the UPDATE above bypassed the identity map

    seen = await latest_check(session, answer_id)

    assert seen.id == check_id and seen.check_result["state"] == "failed"
    assert answer_check_run.STALE_AFTER > ANSWER_CHECK_JOB_TIMEOUT  # a job queued behind others still has its time
