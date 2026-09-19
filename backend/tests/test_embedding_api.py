"""GET /api/embedding's search model fields and POST /api/embedding/model, against a fake Hugging Face (spec §5, §8.3,
§8.5). No network: the files are hub_fakes' two small ones, served by FakeHub."""

import uuid
from contextlib import asynccontextmanager

import pytest
from conftest import parse_sse
from hub_fakes import ONNX_BYTES, TOKENIZER_BYTES, VARIANT, FakeHub

from app.api import embedding as embedding_api
from app.api.deps import get_transport
from app.config import settings
from app.core import chat, embedding_index
from app.main import create_app
from app.models import Chunk, Paper
from app.providers import search_model

pytestmark = pytest.mark.anyio

TOTAL = len(ONNX_BYTES) + len(TOKENIZER_BYTES)


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    """An empty models folder, and the test model as the shipped variant."""
    monkeypatch.setattr(settings, "models_dir", tmp_path)
    monkeypatch.setattr(search_model, "SHIPPED", VARIANT)
    return tmp_path


@pytest.fixture
def hub(app, session, monkeypatch):
    """Hugging Face for the route, and the fresh session the route opens after the download kept in this test's."""
    fake = FakeHub()
    app.dependency_overrides[get_transport] = lambda: fake.transport
    monkeypatch.setattr(search_model, "CHUNK", 512)

    @asynccontextmanager
    async def test_session():
        yield session

    monkeypatch.setattr(embedding_api, "SessionLocal", test_session)
    return fake


async def unembedded_paper(session) -> Paper:
    paper = Paper(
        title=f"Uploaded before the model {uuid.uuid4().hex[:6]}", file_path="/nonexistent.pdf", status="ready"
    )
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(
            paper_id=paper.id,
            ordinal=0,
            page=1,
            bbox=[[1, 2, 3, 4]],
            text="a passage",
            embed_model="test",
            strategy_ver=1,
        )
    )
    await session.commit()
    return paper


def place(models_dir, file: search_model.ModelFile, content: bytes) -> None:
    target = search_model.path(models_dir, file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


async def test_status_says_whether_the_model_is_here_and_what_a_download_would_fetch(client, models_dir):
    def fields(body):
        return body["model_present"], body["download_bytes"]

    assert fields((await client.get("/api/embedding")).json()) == (False, TOTAL)
    place(models_dir, VARIANT.tokenizer, TOKENIZER_BYTES)
    part = search_model.path(models_dir, VARIANT.onnx).with_name("model_int8.onnx.part")
    part.parent.mkdir(parents=True)
    part.write_bytes(ONNX_BYTES[:1024])  # a download that stopped part-way
    assert fields((await client.get("/api/embedding")).json()) == (False, len(ONNX_BYTES) - 1024)
    part.unlink()
    place(models_dir, VARIANT.onnx, ONNX_BYTES)
    assert fields((await client.get("/api/embedding")).json()) == (True, 0)


async def test_status_counts_papers_without_vectors_and_papers_that_need_search(client, session, models_dir):
    await unembedded_paper(session)

    body = (await client.get("/api/embedding")).json()

    assert body["unembedded_papers"] == len(await embedding_index.unembedded_papers(session)) >= 1
    assert body["papers_needing_search"] == await chat.papers_needing_search(session)
    assert {"model", "chunks", "indexed_with"} <= set(body)  # unchanged fields


async def test_a_download_streams_progress_then_queues_every_paper_without_vectors(
    client, session, arq, models_dir, hub
):
    waiting = await unembedded_paper(session)

    response = await client.post("/api/embedding/model")

    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["progress"] * (len(names) - 1) + ["done"]
    progress = [data for name, data in events if name == "progress"]
    assert progress[-1] == {"file": "onnx/model_int8.onnx", "completed": TOTAL, "total": TOTAL}
    queued = await embedding_index.unembedded_papers(session)
    assert events[-1] == ("done", {"papers_queued": len(queued)})
    assert set(arq.jobs) == {("reembed_paper", str(paper_id)) for paper_id in queued}
    assert ("reembed_paper", str(waiting.id)) in arq.jobs
    assert search_model.present(models_dir, VARIANT)


async def test_a_download_that_stops_says_why_and_queues_nothing(client, arq, models_dir, hub):
    hub.offline = True

    events = parse_sse((await client.post("/api/embedding/model")).text)

    # No progress event first: FakeHub.offline raises before search_model._fetch's first yield, which only comes
    # once client.stream() has settled a response (see test_no_network_says_so_and_leaves_nothing_in_place).
    assert events == [("error", {"detail": search_model.NO_NETWORK})]
    assert arq.jobs == []


async def test_a_model_that_arrives_but_cannot_queue_its_papers_says_so(
    client, session, arq, models_dir, hub, monkeypatch
):
    await unembedded_paper(session)

    async def redis_down(*args):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(arq, "enqueue_job", redis_down)

    events = parse_sse((await client.post("/api/embedding/model")).text)

    assert events[-1] == ("error", {"detail": embedding_api.NOT_QUEUED})
    assert search_model.present(models_dir, VARIANT)  # the model itself is in place


async def test_a_download_is_refused_while_the_model_is_here_or_another_one_runs(client, models_dir, hub):
    async with embedding_api._downloading:  # a download already running
        running = await client.post("/api/embedding/model")
    place(models_dir, VARIANT.tokenizer, TOKENIZER_BYTES)
    place(models_dir, VARIANT.onnx, ONNX_BYTES)
    present = await client.post("/api/embedding/model")

    assert (running.status_code, running.json()) == (409, {"detail": "download_running"})
    assert (present.status_code, present.json()) == (409, {"detail": "model_present"})
    assert hub.requests == []


def test_the_download_events_are_in_openapi():
    """openapi-typescript only generates types for schemas listed in components."""
    schemas = create_app().openapi()["components"]["schemas"]

    for name in ["DownloadProgressEvent", "DownloadDoneEvent", "DownloadErrorEvent", "EmbeddingStatusOut"]:
        assert name in schemas
    assert {"model_present", "download_bytes", "unembedded_papers", "papers_needing_search"} <= set(
        schemas["EmbeddingStatusOut"]["properties"]
    )
