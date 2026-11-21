import uuid

import pytest
from sqlalchemy import update
from test_answer_check_run import make_answer
from test_chat_workspace_api import make_paper as make_titled_paper
from test_chat_workspace_api import make_workspace

from app.core import answer_check_run, chat, claims, mcp_reads, queue, workspace_package_answers
from app.core.errors import NotFound
from app.models import LLMConnection, LLMModel, LLMOutput, Workspace
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(claims, "sleep", instant)
    monkeypatch.setattr(queue, "_pool", arq)


def url(output_id) -> str:
    return f"/api/chat/answers/{output_id}/check"


async def test_post_starts_a_check_and_queues_one_job(client, session, arq, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1]. Ask a colleague.", ["It reaches 28.4 BLEU."])

    response = await client.post(url(answer.id), json={})

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "running" and body["model"] == "qwen3:8b"
    assert [s["state"] for s in body["sentences"]] == ["pending", "not_cited"]
    assert [j[0] for j in arq.jobs] == ["check_answer"]
    assert arq.jobs[0][1] == body["id"]


async def test_second_post_while_running_queues_nothing(client, session, arq, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["It reaches 28.4 BLEU."])
    first = (await client.post(url(answer.id), json={})).json()

    again = await client.post(url(answer.id), json={})

    assert again.json()["id"] == first["id"]
    assert len(arq.jobs) == 1


async def test_get_shows_progress_then_the_result(client, session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["It reaches 28.4 BLEU."])
    assert (await client.get(url(answer.id))).status_code == 404
    started = (await client.post(url(answer.id), json={})).json()
    assert (await client.get(url(answer.id))).json()["state"] == "running"

    await answer_check_run.run_check(session, uuid.UUID(started["id"]), llm=FakeLLM())

    body = (await client.get(url(answer.id))).json()
    assert body["state"] == "done" and body["summary"] == "1 supported"
    assert body["sentences"][0]["verdict"] == "supported" and body["sentences"][0]["quote_label"] == "C1"


async def test_refusals(client, session, local_default_model):
    old, _ = await make_answer(session, "Old [C1].", ["text"], snapshot=False)
    response = await client.post(url(old.id), json={})
    assert (response.status_code, response.json()["detail"]) == (409, "answer_not_checkable")
    missing = await client.post(url(uuid.uuid4()), json={})
    assert (missing.status_code, missing.json()["detail"]) == (404, "answer_not_found")


async def test_cloud_model_needs_confirm(client, session, arq):
    await session.execute(update(LLMModel).values(is_default=False))
    cloud = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(cloud)
    await session.flush()
    session.add(LLMModel(connection_id=cloud.id, name="big", is_default=True))
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["It reaches 28.4 BLEU."])

    refused = await client.post(url(answer.id), json={})
    assert refused.status_code == 409 and refused.json()["detail"] == "remote_model_needs_confirm"
    assert "api.example.com" in refused.json()["host"]
    assert arq.jobs == []
    confirmed = await client.post(url(answer.id), json={"confirm_remote": True})
    assert confirmed.status_code == 202 and confirmed.json()["connection_name"] == "Cloud"


async def test_a_read_only_imported_workspace_answer_can_be_checked(client, session, local_default_model):
    paper = await make_titled_paper(session, "Attention Is All You Need")
    workspace = await make_workspace(session, [paper])
    await session.execute(update(Workspace).where(Workspace.id == workspace.id).values(read_only=True))
    answer = LLMOutput(workspace_id=workspace.id, kind="chat", question="q", content="Claim [C1].", model="m",
                       prompt_version=6, source_snapshot=[])
    session.add(answer)
    await session.commit()

    assert (await client.post(url(answer.id), json={})).status_code == 202


async def test_check_rows_stay_out_of_answer_lists(client, session, local_default_model):
    answer, _ = await make_answer(session, "It reaches 28.4 BLEU [C1].", ["It reaches 28.4 BLEU."])
    paper = await make_titled_paper(session, "BERT")
    workspace = await make_workspace(session, [paper])
    ws_answer = LLMOutput(workspace_id=workspace.id, kind="chat", question="q", content="Claim [C1].", model="m",
                          prompt_version=6, source_snapshot=[])
    session.add(ws_answer)
    await session.commit()
    check = (await client.post(url(answer.id), json={})).json()
    ws_check = (await client.post(url(ws_answer.id), json={})).json()

    paper_list = await chat.list_answers(session, answer.paper_id)
    ws_list = await chat.list_answers(session, chat.Scope(workspace_id=workspace.id))
    rows, _ = await workspace_package_answers.export_rows(session, workspace.id, {})
    mcp = await mcp_reads.answers_out(session, paper_id=answer.paper_id, workspace=None, offset=0)

    assert [a.output.id for a in paper_list] == [answer.id]
    assert [a.output.id for a in ws_list] == [ws_answer.id]
    assert [r["content"] for r in rows] == ["Claim [C1]."]  # the check's summary line is not an answer
    assert ws_check["state"] == "running"
    assert [a.id for a in mcp.answers] == [answer.id] and mcp.total == 1
    with pytest.raises(NotFound):
        await chat.load_thread(session, answer.paper_id, uuid.UUID(check["id"]))
