import pytest
from sqlalchemy import delete

from app.models import LLMModel
from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio


def _url(workspace):
    return f"/api/workspaces/{workspace.id}/search/screening"


async def test_state_defaults_and_names_the_default_model(client, session):
    workspace, _ = await make_pool(session, [])
    body = (await client.get(_url(workspace))).json()
    assert body["criteria"] is None
    assert (body["suggest_status"], body["suggest_done"], body["suggest_total"]) == ("idle", 0, 0)
    assert set(body) >= {"model_label", "model_is_local", "model_host"}


async def test_state_without_a_default_model(client, session):
    await session.execute(delete(LLMModel))
    workspace, _ = await make_pool(session, [])
    body = (await client.get(_url(workspace))).json()
    assert (body["model_label"], body["model_is_local"], body["model_host"]) == (None, None, None)


async def test_saving_criteria_clears_stored_suggestions(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", None)])
    hit.suggestion, hit.suggestion_model = "include", "Ollama · qwen3:8b"
    await session.flush()
    resp = await client.put(_url(workspace), json={"criteria": "RCTs on sleep in adults"})
    assert resp.json()["criteria"] == "RCTs on sleep in adults"
    await session.refresh(hit)
    assert (hit.suggestion, hit.suggestion_model) == (None, None)


async def test_saving_the_same_criteria_keeps_suggestions(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", None)])
    workspace.screening_criteria = "RCTs"
    hit.suggestion = "include"
    await session.flush()
    await client.put(_url(workspace), json={"criteria": "RCTs"})
    await session.refresh(hit)
    assert hit.suggestion == "include"


async def test_criteria_over_the_limit_is_422(client, session):
    workspace, _ = await make_pool(session, [])
    assert (await client.put(_url(workspace), json={"criteria": "x" * 4001})).status_code == 422


async def test_blank_criteria_are_stored_as_none(client, session):
    workspace, _ = await make_pool(session, [])
    assert (await client.put(_url(workspace), json={"criteria": "   "})).json()["criteria"] is None


async def test_criteria_cannot_change_while_suggesting(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", None)])
    workspace.suggest_status = "running"
    hit.suggestion = "include"
    await session.flush()
    resp = await client.put(_url(workspace), json={"criteria": "new"})
    assert resp.status_code == 409
    await session.refresh(hit)
    assert hit.suggestion == "include"
