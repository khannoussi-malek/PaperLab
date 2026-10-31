import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from test_manuscript_papers import setup

from app.core import llm_connections, manuscripts, queue
from app.core import manuscript_review as mr
from app.core import manuscript_section_review as msr
from app.core.errors import Conflict
from app.models import LLMConnection, LLMModel, ManuscriptClaimCheck
from app.workers import manuscript_review as review_worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # flips the default model
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


async def test_a_citation_check_whose_default_turns_remote_is_refused_by_the_job(
    session, arq, local_default_model, monkeypatch
):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(review_worker, "SessionLocal", shared_session)
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Walking is good for health in most adults.")
    out = await mr.start(session, m.id, file="main.tex", base=FUTURE, selection=None)  # local: no yes needed
    await _remote(session)
    await review_worker.check_manuscript_citations({}, str(out["id"]))
    found = list(
        await session.scalars(
            select(ManuscriptClaimCheck)
            .where(ManuscriptClaimCheck.run_id == out["id"])
            .execution_options(populate_existing=True)
        )
    )
    assert found and all((c.status, c.reason) == ("failed", "remote_model_needs_confirm") for c in found)


@pytest.fixture
def evidence_wiring(session, embedder, monkeypatch):
    from test_manuscript_evidence import library

    from app.core import retrieval
    from app.workers import manuscript_evidence as evidence_worker

    @asynccontextmanager
    async def shared_session():
        yield session

    async def query_embedder(session, given=None):
        return embedder

    monkeypatch.setattr(evidence_worker, "SessionLocal", shared_session)
    monkeypatch.setattr(retrieval, "query_embedder", query_embedder)
    return library, evidence_worker


async def evidence_rows(session, mid):
    from app.models import ManuscriptEvidence

    found = await session.scalars(
        select(ManuscriptEvidence)
        .where(ManuscriptEvidence.manuscript_id == mid)
        .execution_options(populate_existing=True)
    )
    return list(found)


async def test_find_evidence_needs_a_yes_for_a_remote_default_before_anything_is_found(
    session, embedder, arq, evidence_wiring
):
    from test_manuscript_evidence import SENTENCE

    from app.core import manuscript_evidence as ev

    library, _ = evidence_wiring
    _, m = await library(session, embedder, "Alpha")
    await _remote(session)
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await ev.find(session, m.id, SENTENCE, embedder=embedder)
    assert arq.jobs == [] and await evidence_rows(session, m.id) == []
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder, confirm_remote=True)
    assert out["verdicts"] == "queued" and all(r.confirm_remote for r in await evidence_rows(session, m.id))


async def test_find_evidence_whose_default_turns_remote_is_refused_by_the_job(
    session, embedder, arq, local_default_model, evidence_wiring
):
    from test_manuscript_evidence import SENTENCE

    from app.core import manuscript_evidence as ev

    library, evidence_worker = evidence_wiring
    _, m = await library(session, embedder, "Alpha")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)  # local: no yes needed
    await _remote(session)
    await evidence_worker.verify_manuscript_evidence({}, str(m.id), out["sentence_hash"])
    (row,) = await evidence_rows(session, m.id)
    assert (row.status, row.reason) == ("failed", "remote_model_needs_confirm")
