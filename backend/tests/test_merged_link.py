"""R19: a merged paper's id answers 410 paper_merged with kept_id, so its link leads to the paper it became."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from mcp import Client

from app.models import PaperMerge
from app.providers import embedding
from mcp_server import server

pytestmark = pytest.mark.anyio

ROUTES = ["", "/file", "/chunks", "/notes"]


def audit(kept, gone, status="merged", age=0):
    when = datetime.now(timezone.utc) - timedelta(minutes=age)
    return PaperMerge(kept_id=kept, merged_id=gone, status=status, created_at=when)


@pytest.mark.parametrize("route", ROUTES)
async def test_a_merged_id_answers_410_with_the_kept_id(session, client, route):
    kept, gone = uuid.uuid4(), uuid.uuid4()
    session.add_all([audit(kept, uuid.uuid4(), age=1), audit(kept, gone)])
    await session.flush()

    response = await client.get(f"/api/papers/{gone}{route}")

    assert response.status_code == 410
    assert response.json() == {"detail": "paper_merged", "kept_id": str(kept)}


async def test_the_latest_merge_wins(session, client):
    first, latest, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session.add_all([audit(first, gone, age=5), audit(latest, gone)])
    await session.flush()

    assert (await client.get(f"/api/papers/{gone}")).json()["kept_id"] == str(latest)


async def test_an_unknown_id_is_still_404(client):
    assert (await client.get(f"/api/papers/{uuid.uuid4()}")).status_code == 404


async def test_a_reported_merge_is_a_plain_404(session, client):
    gone = uuid.uuid4()
    session.add(audit(uuid.uuid4(), gone, status="reported"))
    await session.flush()

    response = await client.get(f"/api/papers/{gone}")

    assert response.status_code == 404 and "kept_id" not in response.json()


async def test_mcp_get_paper_says_it_was_merged(session, embedder, monkeypatch):
    @asynccontextmanager
    async def test_session():
        yield session

    monkeypatch.setattr(server, "sessions", test_session)
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)
    kept, gone = uuid.uuid4(), uuid.uuid4()
    session.add(audit(kept, gone))
    await session.flush()

    async with Client(server.mcp) as mcp:
        result = await mcp.call_tool("get_paper", {"paper_id": str(gone)})

    assert result.is_error
    assert result.structured_content == {
        "error": "paper_merged",
        "detail": f"This paper was merged into {kept}.",
        "kept_id": str(kept),
    }
