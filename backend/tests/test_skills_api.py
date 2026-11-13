"""Skills over HTTP and in chat (M17 spec §4, §6). Real Postgres via the app bound to the test session."""

import pytest
from conftest import parse_sse
from sqlalchemy import select
from test_chat_api import make_paper
from test_chat_workspace_api import make_paper as make_workspace_paper
from test_chat_workspace_api import make_workspace, query_model  # noqa: F401 (the fixture is a parameter)

from app.core import chat, skills
from app.models import LLMOutput
from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio

BASE = "/api/skills"


async def create_skill(client, label="Plain check", scope="both", instructions="Be plain about it."):
    response = await client.post(
        BASE, json={"label": label, "description": "d", "scope": scope, "instructions": instructions}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def output_for(session, output_id) -> LLMOutput:
    return (await session.execute(select(LLMOutput).where(LLMOutput.id == output_id))).scalar_one()


# GET / POST / PUT / DELETE / reset / default


async def test_get_lists_the_visible_skills_for_a_chat_kind(client, session):
    response = await client.get(BASE, params={"scope": "paper"})
    assert response.status_code == 200
    expected = [v.id for v in await skills.list_skills(session, kind="paper")]
    assert [s["id"] for s in response.json()] == expected
    assert response.json()[0]["state"] == "builtin"


async def test_hidden_skills_come_back_only_when_asked(client):
    await client.put(f"{BASE}/builtin:study-type", json={"is_listed": False})
    picker = [s["id"] for s in (await client.get(BASE)).json()]
    settings = [s["id"] for s in (await client.get(BASE, params={"include_hidden": "true"})).json()]
    assert "builtin:study-type" not in picker
    assert "builtin:study-type" in settings


async def test_create_returns_a_custom_skill_with_201(client):
    body = await create_skill(client, label="  Spaced label  ")
    assert body["id"].startswith("custom:")
    assert (body["label"], body["state"], body["version"], body["is_listed"]) == ("Spaced label", "custom", 1, True)


async def test_create_with_a_taken_label_is_409(client):
    builtin_label = (await client.get(BASE, params={"include_hidden": "true"})).json()[0]["label"]
    response = await client.post(
        BASE, json={"label": builtin_label.upper(), "description": "", "scope": "paper", "instructions": "x"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "skill_label_taken"


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "x", "description": "", "scope": "nowhere", "instructions": "x"},
        {"label": "x", "description": "", "scope": "paper", "instructions": "x", "surprise": 1},
        {"label": "x", "description": "", "scope": "paper"},
    ],
)
async def test_create_rejects_bad_scope_extra_fields_and_missing_fields_with_422(client, payload):
    assert (await client.post(BASE, json=payload)).status_code == 422


async def test_create_with_an_empty_label_is_422_invalid_input(client):
    response = await client.post(BASE, json={"label": "   ", "description": "", "scope": "paper", "instructions": "x"})
    assert response.status_code == 422
    assert response.json()["detail"] == "skill_label_length"


async def test_put_edits_sent_fields_and_bumps_version_when_instructions_change(client):
    response = await client.put(f"{BASE}/builtin:check-evaluation", json={"instructions": "A new check."})
    assert response.status_code == 200
    body = response.json()
    assert (body["state"], body["version"], body["instructions"]) == ("edited", 2, "A new check.")


async def test_put_rejects_an_unknown_field_with_422(client):
    response = await client.put(f"{BASE}/builtin:check-evaluation", json={"state": "custom"})
    assert response.status_code == 422


async def test_put_to_an_unknown_skill_is_404(client):
    response = await client.put(f"{BASE}/custom:00000000-0000-0000-0000-000000000000", json={"label": "x"})
    assert response.status_code == 404
    assert (await client.put(f"{BASE}/nonsense", json={"label": "x"})).json()["detail"] == "skill_not_found"


async def test_delete_removes_a_custom_skill_with_204(client):
    body = await create_skill(client)
    assert (await client.delete(f"{BASE}/{body['id']}")).status_code == 204
    assert (await client.delete(f"{BASE}/{body['id']}")).json()["detail"] == "skill_not_found"


async def test_delete_of_a_bundled_skill_is_409_builtin_skill(client):
    response = await client.delete(f"{BASE}/builtin:study-type")
    assert response.status_code == 409
    assert response.json()["detail"] == "builtin_skill"


async def test_reset_restores_a_bundled_skill_and_refuses_a_custom_one(client):
    await client.put(f"{BASE}/builtin:check-evaluation", json={"instructions": "Changed."})
    response = await client.post(f"{BASE}/builtin:check-evaluation/reset")
    assert response.status_code == 200
    assert response.json()["state"] == "builtin"
    custom = await create_skill(client)
    response = await client.post(f"{BASE}/{custom['id']}/reset")
    assert (response.status_code, response.json()["detail"]) == (409, "custom_skill")


async def test_default_moves_between_skills_and_refuses_an_out_of_scope_one(client, session):
    first = await create_skill(client, label="First paper")
    second = await create_skill(client, label="Second paper")
    await client.post(f"{BASE}/{first['id']}/default", json={"scope": "paper", "on": True})
    response = await client.post(f"{BASE}/{second['id']}/default", json={"scope": "paper", "on": True})
    assert response.status_code == 200 and response.json()["is_paper_default"] is True
    listed = {s["id"]: s for s in (await client.get(BASE, params={"scope": "paper"})).json()}
    assert not listed[first["id"]]["is_paper_default"]
    paper_only = await create_skill(client, label="Paper only", scope="paper")
    response = await client.post(f"{BASE}/{paper_only['id']}/default", json={"scope": "workspace", "on": True})
    assert (response.status_code, response.json()["detail"]) == (409, "skill_scope")


async def test_default_rejects_an_unknown_chat_kind_with_422(client):
    response = await client.post(f"{BASE}/builtin:study-type/default", json={"scope": "both", "on": True})
    assert response.status_code == 422


# Chat with a skill


async def test_paper_chat_with_a_skill_sends_the_composed_prompt_and_saves_its_label_and_version(
    client, session, fake_llm
):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    skill = await create_skill(client, label="Plain check", instructions="Be plain about it.")

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "Why?", "skill_id": skill["id"]})

    assert response.status_code == 200
    system, _ = fake_llm.calls[0]
    assert system == f"{chat.SYSTEM_PROMPT}\n\nYour task for this question:\nBe plain about it."
    done = parse_sse(response.text)[-1][1]
    assert done["skill_label"] == "Plain check"
    output = await output_for(session, done["output_id"])
    assert (output.skill_label, output.skill_version) == ("Plain check", 1)


async def test_paper_chat_without_a_skill_keeps_the_base_prompt_byte_identical(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "Why?"})

    assert fake_llm.calls[0][0] == chat.SYSTEM_PROMPT
    done = parse_sse(response.text)[-1][1]
    assert done["skill_label"] is None
    assert (await output_for(session, done["output_id"])).skill_label is None


async def test_a_follow_up_uses_the_skill_picked_for_that_question(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    first_skill = await create_skill(client, label="First task", instructions="Task one.")
    second_skill = await create_skill(client, label="Second task", instructions="Task two.")
    first = parse_sse(
        (
            await client.post(f"/api/papers/{paper.id}/chat", json={"question": "One?", "skill_id": first_skill["id"]})
        ).text
    )[-1][1]

    await client.post(
        f"/api/papers/{paper.id}/chat",
        json={"question": "Two?", "skill_id": second_skill["id"], "parent_id": first["output_id"]},
    )

    assert fake_llm.calls[0][0].endswith("Your task for this question:\nTask one.")
    assert fake_llm.calls[1][0].endswith("Your task for this question:\nTask two.")


async def test_an_answer_keeps_the_label_it_ran_with_after_the_skill_is_renamed_or_deleted(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    skill = await create_skill(client, label="Old name")
    await client.post(f"/api/papers/{paper.id}/chat", json={"question": "Why?", "skill_id": skill["id"]})

    await client.put(f"{BASE}/{skill['id']}", json={"label": "New name"})
    [answer] = (await client.get(f"/api/papers/{paper.id}/chat")).json()
    assert answer["skill_label"] == "Old name"
    await client.delete(f"{BASE}/{skill['id']}")
    [answer] = (await client.get(f"/api/papers/{paper.id}/chat")).json()
    assert answer["skill_label"] == "Old name"


async def test_a_chat_with_an_unknown_or_out_of_scope_skill_is_refused_before_streaming(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    paper_only = await create_skill(client, label="Paper only", scope="paper")

    unknown = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "?", "skill_id": "custom:nope"})
    workspace_only = await create_skill(client, label="Workspace only", scope="workspace")
    outside = await client.post(
        f"/api/papers/{paper.id}/chat", json={"question": "?", "skill_id": workspace_only["id"]}
    )
    workspace = await make_workspace_paper(session, "Only")
    ws = await make_workspace(session, [workspace])
    ws_refused = await client.post(
        f"/api/workspaces/{ws.id}/chat", json={"question": "?", "skill_id": paper_only["id"]}
    )

    assert (unknown.status_code, unknown.json()["detail"]) == (404, "skill_not_found")
    assert (outside.status_code, outside.json()["detail"]) == (409, "skill_scope")
    assert (ws_refused.status_code, ws_refused.json()["detail"]) == (409, "skill_scope")
    assert fake_llm.calls == []


async def test_a_workspace_chat_with_a_both_skill_composes_the_workspace_prompt(client, session, fake_llm, query_model):  # noqa: F811 (the fixture)
    first = await make_workspace_paper(session, "DPR")
    workspace = await make_workspace(session, [first])
    skill = await create_skill(client, label="Both task", scope="both", instructions="Compare them.")

    response = await client.post(
        f"/api/workspaces/{workspace.id}/chat", json={"question": "Compare", "skill_id": skill["id"]}
    )

    assert response.status_code == 200
    system, _ = fake_llm.calls[0]
    assert system.endswith("\n\nYour task for this question:\nCompare them.")
    assert system.startswith(chat.WORKSPACE_SYSTEM_PROMPT)
    assert parse_sse(response.text)[-1][1]["skill_label"] == "Both task"


async def test_a_hit_chat_that_names_a_skill_is_refused_with_skill_not_here(
    client, session, fake_llm, local_default_model
):
    workspace, [hit] = await make_pool(session, [("Sleep helps memory.", None)])
    await session.commit()
    skill = await create_skill(client)

    response = await client.post(
        f"/api/workspaces/{workspace.id}/search/hits/{hit.id}/chat",
        json={"question": "What helps?", "skill_id": skill["id"]},
    )

    assert (response.status_code, response.json()["detail"]) == (422, "skill_not_here")
    assert fake_llm.calls == []
