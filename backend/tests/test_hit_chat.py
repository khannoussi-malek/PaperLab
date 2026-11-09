import uuid

import pytest
from conftest import parse_sse
from test_chat_api import make_paper

from app.core import hit_chat
from app.providers.llm import FAKE_ANSWER
from tests.screening_pool import make_pool

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("local_default_model")]


def url(workspace, hit):
    return f"/api/workspaces/{workspace.id}/search/hits/{hit.id}/chat"


async def test_hit_chat_abstract_only_marks_source(client, session, fake_llm):
    workspace, [hit] = await make_pool(session, [("Sleep helps memory.", None)])
    await session.commit()

    response = await client.post(url(workspace, hit), json={"question": "What helps memory?"})

    events = parse_sse(response.text)
    assert response.status_code == 200
    assert events[0] == ("meta", {"source": "abstract"})
    assert events[-1][0] == "done"
    assert "".join(d["text"] for n, d in events if n == "token") == FAKE_ANSWER
    system, prompt = fake_llm.calls[0]
    assert "[abstract]" in system and "page" in system.lower()
    assert "Sleep helps memory." in prompt and "paper 0" in prompt
    [answer] = (await client.get(url(workspace, hit))).json()
    assert (answer["question"], answer["content"]) == ("What helps memory?", FAKE_ANSWER)
    assert hit_chat.HISTORY.pop(hit.id)


async def test_hit_chat_delegates_to_paper_chat_when_full_text(client, session, fake_llm):
    workspace, [hit] = await make_pool(session, [("Abstract text.", None)])
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    await session.refresh(paper)
    paper_id = paper.id
    hit.paper_id = paper_id
    await session.commit()

    response = await client.post(url(workspace, hit), json={"question": "What is the method?"})

    events = parse_sse(response.text)
    assert events[0] == ("meta", {"source": "full_text"})
    assert events[1][0] == "sources" and len(events[1][1]["sources"]) == 2
    assert "Method text." in fake_llm.calls[0][1]
    [answer] = (await client.get(url(workspace, hit))).json()
    assert answer["question"] == "What is the method?"
    assert (await client.get(f"/api/papers/{paper_id}/chat")).json()[0]["id"] == answer["id"]


async def test_hit_chat_foreign_hit_404(client, session, fake_llm):
    workspace, [hit] = await make_pool(session, [("x", None)])
    other, _ = await make_pool(session, [("y", None)])
    await session.commit()

    for method in (client.post, client.get):
        kwargs = {"json": {"question": "q"}} if method == client.post else {}
        assert (await method(url(other, hit), **kwargs)).status_code == 404
    missing = f"/api/workspaces/{workspace.id}/search/hits/{uuid.uuid4()}/chat"
    assert (await client.post(missing, json={"question": "q"})).status_code == 404


async def first_answer(client, workspace, hit):
    await client.post(url(workspace, hit), json={"question": "First question?"})
    return (await client.get(url(workspace, hit))).json()[0]["id"]


async def test_abstract_follow_up_carries_the_earlier_question(client, session, fake_llm):
    workspace, [hit] = await make_pool(session, [("Sleep helps memory.", None)])
    await session.commit()
    parent = await first_answer(client, workspace, hit)

    await client.post(url(workspace, hit), json={"question": "And then?", "parent_id": parent})

    system, prompt = fake_llm.calls[1]
    assert "First question?" in prompt and FAKE_ANSWER[:20] in prompt
    assert "abstract only" in fake_llm.calls[0][0] and "abstract only" not in system
    bad = await client.post(url(workspace, hit), json={"question": "x", "parent_id": str(uuid.uuid4())})
    assert (bad.status_code, bad.json()) == (404, {"detail": "parent_not_found"})
    hit_chat.HISTORY.pop(hit.id)


async def test_history_is_capped_per_hit_and_in_hits():
    hit_id = uuid.uuid4()
    for i in range(hit_chat.MAX_ANSWERS_PER_HIT + 5):
        hit_chat.remember(hit_id, f"q{i}", "a", "m", "c", None)
    kept = hit_chat.HISTORY[hit_id]
    assert (len(kept), kept[0].question) == (hit_chat.MAX_ANSWERS_PER_HIT, "q5")
    for _ in range(hit_chat.MAX_HITS):
        hit_chat.remember(uuid.uuid4(), "q", "a", "m", "c", None)
    assert hit_id not in hit_chat.HISTORY and len(hit_chat.HISTORY) == hit_chat.MAX_HITS
    hit_chat.HISTORY.clear()


async def test_abstract_parent_is_ignored_once_the_hit_has_full_text(client, session, fake_llm):
    workspace, [hit] = await make_pool(session, [("Abstract text.", None)])
    await session.commit()
    parent = await first_answer(client, workspace, hit)
    paper, _ = await make_paper(session, ["Intro text."])
    await session.refresh(paper)
    hit = await session.get(type(hit), hit.id)
    hit.paper_id = paper.id
    await session.commit()

    response = await client.post(url(workspace, hit), json={"question": "Again?", "parent_id": parent})

    assert response.status_code == 200
    assert parse_sse(response.text)[0] == ("meta", {"source": "full_text"})
    hit_chat.HISTORY.clear()


async def test_hit_chat_without_a_default_model_is_409(client, session):
    from sqlalchemy import update

    from app.models import LLMModel

    workspace, [hit] = await make_pool(session, [("x", None)])
    await session.commit()
    await session.execute(update(LLMModel).values(is_default=False))
    response = await client.post(url(workspace, hit), json={"question": "q"})
    assert (response.status_code, response.json()) == (409, {"detail": "no_model"})
