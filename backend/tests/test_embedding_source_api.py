"""The search source over HTTP (D156–D158): the status's new fields, the switch and its probe, Try again, and no key
in any answer or log record. Every provider is FakeEmbeddings: no network."""

import logging
import uuid
from dataclasses import astuple

import pytest
from embedder_fakes import COMPAT_URL, KEY, OLLAMA_URL, OPENAI_URL, FakeEmbeddings
from sqlalchemy import delete
from test_embedding_index import indexed_paper, worker_uses
from test_search_rebuild import OLLAMA_NAME, paper_with, switched

from app.api.deps import get_transport
from app.core import embedding_index, embedding_sources
from app.main import create_app
from app.models import Chunk
from app.providers import embedding
from app.workers import ingest

pytestmark = pytest.mark.anyio

OPENAI_NAME = "openai/text-embedding-3-small@768"
PROBE = "PaperLab checks that this search source works."
NOT_QUEUED = "Search now uses OpenAI, but your papers couldn't be queued. Press Try again in Settings → Search."
WRONG_SIZE = (
    "bge-m3 gives vectors of 1,024 numbers, and PaperLab's search index holds 768. Choose a model that gives 768, "
    "such as nomic-embed-text."
)


@pytest.fixture
def server(app):
    """Every provider the routes call, behind FakeEmbeddings."""
    fake = FakeEmbeddings()
    app.dependency_overrides[get_transport] = lambda: fake.transport
    return fake


async def connection(client, kind: str, base_url: str) -> dict:
    body = {"kind": kind, "label": f"Search API {uuid.uuid4().hex[:8]}", "base_url": base_url}
    if kind != "ollama":
        body["api_key"] = KEY
    response = await client.post("/api/llm/connections", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def pick(kind: str, connection_id: str | None, model: str | None = None) -> dict:
    return {"kind": kind, "connection_id": connection_id, "model": model, "confirm": True}


async def test_a_switch_probes_saves_starts_the_rebuild_and_queues_every_paper_not_on_the_new_source(
    client, session, arq, server
):
    openai = await connection(client, "openai_compatible", OPENAI_URL)
    moved = await indexed_paper(session, OPENAI_NAME)
    waiting = await indexed_paper(session, "test")

    response = await client.put("/api/embedding/source", json=pick("openai", openai["id"], "text-embedding-3-small"))

    to_embed = await embedding_index.papers_to_embed(session, OPENAI_NAME)
    assert (response.status_code, response.json()) == (202, {"papers": len(to_embed)})
    assert set(arq.jobs) == {("reembed_paper", str(paper_id), True) for paper_id in to_embed}
    assert ("reembed_paper", str(waiting.id), True) in arq.jobs
    assert ("reembed_paper", str(moved.id), True) not in arq.jobs
    source = await embedding_sources.active(session)
    assert (source.kind, source.name, source.rebuild_model, source.error) == ("openai", OPENAI_NAME, OPENAI_NAME, None)
    assert source.rebuild_started_at is not None
    assert server.bodies() == [  # one fixed question, never library text
        {"model": "text-embedding-3-small", "input": [PROBE], "encoding_format": "float", "dimensions": 768}
    ]


@pytest.mark.parametrize(
    ("kind", "base_url", "model", "setup", "status", "detail"),
    [
        ("openai", OPENAI_URL, "text-embedding-3-small", {"statuses": [401]}, 502, "Key rejected by OpenAI"),
        ("openai_compatible", COMPAT_URL, "bge-m3", {"dims": 1024}, 422, WRONG_SIZE),
        ("ollama", OLLAMA_URL, None, {"not_pulled": True}, 409, "embedding_model_not_pulled"),
    ],
)
async def test_a_probe_that_fails_changes_nothing(
    client, session, arq, server, kind, base_url, model, setup, status, detail
):
    linked = await connection(client, "ollama" if kind == "ollama" else "openai_compatible", base_url)
    for field, value in setup.items():
        setattr(server, field, value)

    response = await client.put("/api/embedding/source", json=pick(kind, linked["id"], model))

    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert (await embedding_sources.active(session)).kind == "builtin"
    assert arq.jobs == []


async def test_built_in_without_its_model_is_refused_before_anything_changes(client, session, arq, monkeypatch):
    openai = await connection(client, "openai_compatible", OPENAI_URL)
    chosen = await embedding_sources.candidate(session, "openai", uuid.UUID(openai["id"]), None)
    await embedding_sources.save(session, chosen)
    monkeypatch.setattr(embedding, "get_model", lambda: None)  # not downloaded: picking Built-in never downloads it

    response = await client.put("/api/embedding/source", json=pick("builtin", None))

    assert (response.status_code, response.json()) == (409, {"detail": "search_model_missing"})
    assert (await embedding_sources.active(session)).kind == "openai"
    assert arq.jobs == []


async def test_the_source_already_in_use_is_200_and_queues_nothing(client, arq, server):
    response = await client.put("/api/embedding/source", json=pick("builtin", None))

    assert (response.status_code, response.json()) == (200, {"papers": 0})
    assert (arq.jobs, server.requests) == ([], [])


async def test_papers_that_cannot_be_queued_after_the_switch_say_so_and_leave_try_again(
    client, session, arq, server, monkeypatch
):
    openai = await connection(client, "openai_compatible", OPENAI_URL)
    await indexed_paper(session, "test")

    async def redis_down(*args):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(arq, "enqueue_job", redis_down)

    response = await client.put("/api/embedding/source", json=pick("openai", openai["id"]))

    assert (response.status_code, response.json()) == (503, {"detail": NOT_QUEUED})
    source = await embedding_sources.active(session)
    assert (source.kind, source.error) == ("openai", NOT_QUEUED)  # saved; Settings shows it with Try again


async def test_a_pick_that_does_not_suit_is_refused_before_any_request(client, server):
    openrouter = await connection(client, "openai_compatible", "https://openrouter.ai/api/v1")

    not_openai = await client.put("/api/embedding/source", json=pick("openai", openrouter["id"]))
    unknown = await client.put("/api/embedding/source", json=pick("ollama", str(uuid.uuid4())))
    unconfirmed = await client.put("/api/embedding/source", json={"kind": "builtin"})
    elsewhere = await client.put("/api/embedding/source", json={**pick("builtin", None), "kind": "voyage"})

    assert (not_openai.status_code, not_openai.json()) == (
        422, {"detail": f"{openrouter['label']} can't be used for OpenAI search."}
    )  # fmt: skip
    assert (unknown.status_code, unknown.json()) == (404, {"detail": "connection_not_found"})
    assert (unconfirmed.status_code, elsewhere.status_code, server.requests) == (422, 422, [])


async def test_status_names_the_source_its_rebuild_its_last_error_and_the_library_size(client, session):
    body = (await client.get("/api/embedding")).json()

    assert body["source"] == {
        "kind": "builtin", "connection_id": None, "connection_label": None, "model": None, "host": None,
        "is_local": True, "label": "Built-in",
    }  # fmt: skip
    assert (body["rebuild"], body["source_error"]) == (None, None)
    size = astuple(await embedding_index.library_size(session))
    assert (body["library_papers"], body["library_notes"], body["library_chars"]) == size

    await session.execute(delete(Chunk))  # D15: from here the rebuild counts only this test's papers
    await paper_with(session, OLLAMA_NAME)
    await paper_with(session, "test")
    source = await switched(session)
    await embedding_sources.record_error(session, "Can't reach ollama.test")
    body = (await client.get("/api/embedding")).json()

    assert body["model"] == OLLAMA_NAME
    assert body["source"] == {
        "kind": "ollama", "connection_id": str(source.connection_id), "connection_label": source.label,
        "model": "nomic-embed-text", "host": "ollama.test", "is_local": False, "label": source.label,
    }  # fmt: skip
    assert (body["rebuild"], body["source_error"]) == ({"done": 1, "total": 2}, "Can't reach ollama.test")


async def test_try_again_queues_only_what_is_missing_clears_the_error_and_restarts_the_rebuild(client, session, arq):
    waiting = await indexed_paper(session, "old-model")
    await embedding_sources.record_error(session, "Key rejected by OpenAI")

    again = await client.post("/api/embedding/reindex", json={"confirm": True, "missing_only": True})
    to_embed = await embedding_index.papers_to_embed(session, "test")
    everything = await client.post("/api/embedding/reindex", json={"confirm": True})
    indexed = await embedding_index.indexed_papers(session)

    assert (again.status_code, again.json()) == (202, {"papers": len(to_embed)})
    assert everything.json() == {"papers": len(indexed)}
    assert {job for job in arq.jobs if job[2]} == {("reembed_paper", str(p), True) for p in to_embed}
    assert {job for job in arq.jobs if not job[2]} == {("reembed_paper", str(p), False) for p in indexed}
    assert ("reembed_paper", str(waiting.id), True) in arq.jobs
    source = await embedding_sources.active(session)
    assert (source.error, source.rebuild_model) == (None, "test")
    assert source.rebuild_started_at is not None


def test_the_search_source_schemas_are_in_openapi():
    """openapi-typescript only generates types for schemas listed in components; `kind` is a Literal (Correction 9)."""
    schemas = create_app().openapi()["components"]["schemas"]

    assert {"SearchSourceIn", "SearchSourceOut", "RebuildOut"} <= set(schemas)
    assert {"source", "rebuild", "source_error", "library_papers", "library_notes", "library_chars"} <= set(
        schemas["EmbeddingStatusOut"]["properties"]
    )
    assert "missing_only" in schemas["ReindexRequest"]["properties"]
    assert schemas["SearchSourceIn"]["properties"]["kind"]["enum"] == [
        "builtin", "ollama", "openai", "gemini", "openai_compatible"
    ]  # fmt: skip


async def test_a_stored_key_appears_in_no_embedding_answer_and_no_log_record(
    client, session, arq, server, caplog, monkeypatch
):
    caplog.set_level(logging.DEBUG)
    bodies: list[str] = []

    async def call(method: str, path: str, **kwargs):
        response = await client.request(method, f"/api/embedding{path}", **kwargs)
        bodies.append(response.text)
        return response

    openai = await connection(client, "openai_compatible", OPENAI_URL)
    chosen = pick("openai", openai["id"])
    server.statuses = [401]
    assert (await call("PUT", "/source", json=chosen)).status_code == 502
    server.statuses = [400]  # the answer echoes the key
    assert (await call("PUT", "/source", json=chosen)).status_code == 502
    assert (await call("PUT", "/source", json={**chosen, "api_key": KEY})).status_code == 422  # never echoed back
    assert (await call("PUT", "/source", json=chosen)).status_code == 202
    await call("POST", "/reindex", json={"confirm": True, "missing_only": True})
    # The worker embeds with the stored key, and the answer echoes it.
    server.statuses = [400]
    paper = await indexed_paper(session, "test")
    worker_uses(session, monkeypatch)
    await ingest.reembed_paper({"transport": server.transport}, str(paper.id))
    await call("GET", "")

    assert len(bodies) == 6  # every call above ran
    assert [body for body in bodies if KEY in body] == []
    assert KEY not in caplog.text
    assert "OpenAI returned 400: Incorrect API key provided: ••••" in caplog.text  # logged, masked
