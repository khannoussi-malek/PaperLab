import asyncio
import json

import pytest

from app.core import hit_suggest
from app.core.errors import Conflict, NotFound
from app.core.screening_suggest import SCREENING_PROMPT_VERSION
from app.providers.llm import FakeLLM
from tests.screening_pool import make_pool

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("local_default_model")]

REPLY = json.dumps({"relevance": 4, "decision": "include", "reason": None, "quotes": [], "why": "fits"})


class OneReply(FakeLLM):
    def __init__(self, reply=REPLY, delay=0):
        super().__init__(model="one")
        self.reply, self.delay = reply, delay

    async def stream(self, system, prompt):
        await asyncio.sleep(self.delay)
        yield self.reply


@pytest.fixture
def use_llm(monkeypatch):
    def use(llm):
        monkeypatch.setattr(hit_suggest, "build_llm", lambda connection, name, transport=None: llm)
    return use


async def _pool(session, status="idle", question="Does sleep matter?"):
    workspace, hits = await make_pool(session, [("a trial of sleep", None)])
    workspace.research_question, workspace.suggest_status = question, status
    await session.flush()
    return workspace, hits[0]


async def test_suggest_one_writes_fields(session, use_llm):
    use_llm(OneReply())
    workspace, hit = await _pool(session)
    out = await hit_suggest.suggest_one(session, workspace.id, hit.id, allow_remote=False)
    await session.refresh(hit)
    assert (hit.suggestion, hit.suggestion_relevance, hit.suggestion_prompt_version) == ("include", 4, SCREENING_PROMPT_VERSION)
    assert hit.suggestion_model and hit.suggested_at and hit.stage1_status is None
    assert out["suggestion"] == "include"


async def test_suggest_one_needs_criteria(session, use_llm):
    use_llm(OneReply())
    workspace, hit = await _pool(session, question=None)
    with pytest.raises(Conflict, match="needs_criteria"):
        await hit_suggest.suggest_one(session, workspace.id, hit.id, allow_remote=False)


async def test_suggest_one_refuses_while_prescreen_runs(session, use_llm):
    use_llm(OneReply())
    workspace, hit = await _pool(session, status="running")
    with pytest.raises(Conflict, match="prescreen_running"):
        await hit_suggest.suggest_one(session, workspace.id, hit.id, allow_remote=False)


async def test_suggest_one_foreign_hit_404(session, use_llm, client):
    use_llm(OneReply())
    workspace, hit = await _pool(session)
    other, _ = await _pool(session)
    with pytest.raises(NotFound):
        await hit_suggest.suggest_one(session, other.id, hit.id, allow_remote=False)
    resp = await client.post(f"/api/workspaces/{other.id}/search/hits/{hit.id}/suggest")
    assert resp.status_code == 404
    ok = await client.post(f"/api/workspaces/{workspace.id}/search/hits/{hit.id}/suggest")
    assert (ok.status_code, ok.json()["suggestion"]) == (200, "include")


async def test_suggest_one_timeout_keeps_old_suggestion(session, use_llm, monkeypatch):
    monkeypatch.setattr(hit_suggest, "SUGGEST_TIMEOUT", 0.05)
    use_llm(OneReply(delay=1))
    workspace, hit = await _pool(session)
    hit.suggestion = "exclude"
    await session.flush()
    with pytest.raises(Conflict, match="suggest_timeout"):
        await hit_suggest.suggest_one(session, workspace.id, hit.id, allow_remote=False)
    await session.refresh(hit)
    assert hit.suggestion == "exclude"
