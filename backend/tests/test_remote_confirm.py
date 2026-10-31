import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from test_manuscript_papers import setup

from app.core import llm_connections, manuscripts, queue
from app.core import manuscript_review as mr
from app.core import manuscript_section_review as msr
from app.core.errors import Conflict
from app.models import LLMConnection, LLMModel

pytestmark = pytest.mark.anyio
FUTURE = datetime.now(UTC) + timedelta(days=1)


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def test_local_passes_and_no_model_refuses(session, local_default_model):
    await llm_connections.refuse_unconfirmed_remote(session, False)
    await session.execute(update(LLMModel).values(is_default=False))
    with pytest.raises(Conflict, match="no_model"):
        await llm_connections.refuse_unconfirmed_remote(session, True)


async def _remote(session):
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()


async def test_remote_default_refuses_until_confirmed(session):
    await _remote(session)
    with pytest.raises(Conflict, match="remote_model_needs_confirm") as exc:
        await llm_connections.refuse_unconfirmed_remote(session, False)
    assert exc.value.details == {"model": "Cloud · big", "host": "api.example.com"}
    await llm_connections.refuse_unconfirmed_remote(session, True)


async def test_citation_check_start_refuses_a_remote_model_without_confirm(session, arq):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Walking is good for health in most adults.")
    await _remote(session)
    kw = {"file": "main.tex", "base": FUTURE, "selection": None}
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await mr.start(session, m.id, **kw)
    assert arq.jobs == []
    assert (await mr.start(session, m.id, **kw, confirm_remote=True))["status"] == "queued"


async def test_citation_check_start_runs_a_local_model_without_asking(session, local_default_model):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Walking is good for health in most adults.")
    out = await mr.start(session, m.id, file="main.tex", base=FUTURE, selection=None)
    assert out["status"] == "queued"


async def test_section_review_start_refuses_a_remote_model_without_confirm(session, arq):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", "\\section{Introduction}\nWalking is good for health.\n")
    await _remote(session)
    kw = {"file": "main.tex", "base": FUTURE, "at": 5, "role": None}
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await msr.start(session, m.id, **kw, confirm_remote=False)
    assert arq.jobs == []
    assert (await msr.start(session, m.id, **kw, confirm_remote=True))["status"] == "queued"
