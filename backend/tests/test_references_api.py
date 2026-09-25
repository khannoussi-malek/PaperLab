import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from conftest import FakeEmbedder
from sqlalchemy import delete, select

from app.api.deps import get_discovery
from app.core import embedding_sources, references
from app.models import ExternalRef, Note, NoteEmbedding, Paper, PaperSources, paper_references
from app.workers import references as references_worker

# Fetches and embeds take one advisory lock (core/references.py); in a test it lasts until the rollback, so these
# files share one xdist worker, or two of them deadlock on the same stored reference.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

READER_DOI = "10.5555/m75-api-reader"
PDF = b"%PDF-1.7\n%an imported reference\n"


@pytest.fixture
async def library(session):
    # The dev database (D15) may hold the owner's references, notes and paper sources row; hide them here.
    for model in (paper_references, NoteEmbedding, ExternalRef, Note, PaperSources):
        await session.execute(delete(model))
    return session


async def reader_with_references(session) -> tuple[Paper, ExternalRef, ExternalRef]:
    reader = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI, references_state="ready")
    free = ExternalRef(title="Free reference", doi="10.5555/m75-api-free", pdf_urls=["https://pdf.example/free.pdf"])
    closed = ExternalRef(title="Closed reference", cited_by_count=50)
    session.add_all([reader, free, closed])
    await session.flush()
    await session.execute(
        paper_references.insert(),
        [
            {"paper_id": reader.id, "ref_id": free.id, "direction": "cites", "position": 0},
            {"paper_id": reader.id, "ref_id": closed.id, "direction": "cited_by", "position": 0},
        ],
    )
    return reader, free, closed


async def test_the_listing_has_its_state_summary_and_ranked_rows_and_never_a_vector(client, library):
    reader, free, _ = await reader_with_references(library)

    cites = await client.get(f"/api/papers/{reader.id}/references")
    cited_by = await client.get(f"/api/papers/{reader.id}/references", params={"direction": "cited_by"})

    assert cites.status_code == 200
    body = cites.json()
    assert (body["state"], body["direction"], body["summary"]) == (
        "ready",
        "cites",
        {"cited_by_3plus": 0, "with_pdf": 1},
    )
    assert [(r["title"], r["has_pdf"], r["cocitation"], r["paper_id"]) for r in body["rows"]] == [
        ("Free reference", True, 1, None)
    ]
    assert "embedding" not in cites.text
    assert [r["title"] for r in cited_by.json()["rows"]] == ["Closed reference"]


@pytest.mark.parametrize(("path", "status"), [("references?direction=sideways", 422), ("references", 404)])
async def test_a_bad_direction_is_422_and_an_unknown_paper_404(client, library, path, status):
    paper_id = uuid.uuid4() if status == 404 else (await reader_with_references(library))[0].id

    assert (await client.get(f"/api/papers/{paper_id}/{path}")).status_code == status


async def test_refresh_queues_one_fetch_while_a_fetch_is_running(client, library, arq):
    reader, _, _ = await reader_with_references(library)

    first = await client.post(f"/api/papers/{reader.id}/references/refresh")
    second = await client.post(f"/api/papers/{reader.id}/references/refresh")

    assert (first.status_code, first.json(), second.status_code) == (202, {"state": "fetching"}, 202)
    assert arq.jobs == [("fetch_references", str(reader.id))]
    assert (await client.post(f"/api/papers/{uuid.uuid4()}/references/refresh")).status_code == 404


@pytest.fixture
def discovery_api(app, discovery_fakes):
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers
    return discovery_fakes


async def test_import_downloads_files_in_the_workspace_and_enqueues_ingest(client, library, discovery_api, arq):
    _, free, _ = await reader_with_references(library)
    discovery_api.pdf_host.reply("/free.pdf", 200, content=PDF)
    workspace = (await client.post("/api/workspaces", json={"name": f"m75 {uuid.uuid4().hex[:8]}"})).json()

    response = await client.post(f"/api/references/{free.id}/import", json={"workspace_id": workspace["id"]})

    assert response.status_code == 201
    paper = response.json()
    assert (paper["doi"], paper["workspace_ids"]) == ("10.5555/m75-api-free", [workspace["id"]])
    assert arq.jobs == [("ingest_paper", paper["id"])]
    again = await client.post(f"/api/references/{free.id}/import", json={})
    assert (again.status_code, again.json()["detail"]) == (409, "This paper is already in your library.")


@pytest.mark.parametrize("case", ["closed", "unknown-ref", "unknown-workspace"])
async def test_import_refusals(client, library, discovery_api, arq, case):
    _, free, closed = await reader_with_references(library)
    ref_id = {"closed": closed.id, "unknown-ref": uuid.uuid4(), "unknown-workspace": free.id}[case]
    body = {"workspace_id": str(uuid.uuid4())} if case == "unknown-workspace" else {}

    response = await client.post(f"/api/references/{ref_id}/import", json=body)

    assert response.status_code == (409 if case == "closed" else 404)
    assert arq.jobs == [] and discovery_api.pdf_host.requests == []


# --- the worker job ----------------------------------------------------------------------------------------------


@pytest.fixture
def worker(library, monkeypatch, embedder):
    @asynccontextmanager
    async def shared_session():
        yield library

    monkeypatch.setattr(references_worker, "SessionLocal", shared_session)
    return {"embedder": embedder}


def sources_transport(references_status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/references"):
            if references_status != 200:
                return httpx.Response(references_status, json={"error": "Paper not found"})
            record = {"paperId": "b" * 40, "title": "Worker reference", "externalIds": {}, "openAccessPdf": {"url": ""}}
            return httpx.Response(200, json={"offset": 0, "data": [{"citedPaper": record}]})
        if path.endswith("/citations"):
            return httpx.Response(200, json={"offset": 0, "data": []})
        return httpx.Response(404, json={"error": f"unrouted {request.url}"})

    return httpx.MockTransport(handle)


async def test_the_worker_fetch_stores_embeds_and_marks_ready(library, worker, embedder):
    reader = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI, references_state="fetching")
    library.add(reader)
    await library.flush()

    await references_worker.fetch_references({**worker, "transport": sources_transport()}, str(reader.id))

    await library.refresh(reader)
    assert (reader.references_state, reader.references_error) == ("ready", None)
    [ref] = await library.scalars(select(ExternalRef))
    assert (ref.title, ref.title_embedding is not None) == ("Worker reference", True)
    assert embedder.calls[0][0] == ["search_document: Worker reference"]


async def test_the_worker_fetch_reaches_ready_when_embedding_fails(library, worker, caplog):
    reader = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI, references_state="fetching")
    library.add(reader)
    await library.flush()
    refusing = FakeEmbedder(label="Ollama", refuse="Can't reach ollama.test")

    with caplog.at_level("WARNING", logger="app.workers.references"):
        ctx = {**worker, "embedder": refusing, "transport": sources_transport()}
        await references_worker.fetch_references(ctx, str(reader.id))

    await library.refresh(reader)
    assert (reader.references_state, reader.references_error) == ("ready", None)  # ranked without note similarity
    assert (
        f"the references of {reader.id} weren't embedded, so the tab ranks without note similarity: "
        "Can't reach ollama.test"
    ) in caplog.text
    assert (await embedding_sources.active(library)).error is None  # no paper lacks vectors because of it (D155)


async def test_the_worker_marks_failed_with_the_reason_and_the_paper_stays_usable(library, worker):
    reader = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI, status="ready")
    library.add(reader)
    await library.commit()  # the worker's rollback must not undo the test's own paper (a savepoint in tests)
    reader_id = reader.id

    await references_worker.fetch_references({**worker, "transport": sources_transport(404)}, str(reader_id))

    reader = await library.get(Paper, reader_id, populate_existing=True)
    assert (reader.status, reader.references_state, reader.references_error) == (
        "ready", "failed", references.REFERENCES_UNKNOWN
    )  # fmt: skip


async def test_an_unexpected_error_marks_failed_with_a_generic_message(library, worker, monkeypatch):
    reader = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI)
    library.add(reader)
    await library.commit()  # see above
    reader_id = reader.id

    async def broken(*_):
        raise RuntimeError("a bug")

    monkeypatch.setattr(references, "fetch", broken)
    await references_worker.fetch_references({**worker, "transport": sources_transport()}, str(reader_id))

    reader = await library.get(Paper, reader_id, populate_existing=True)
    assert (reader.references_state, reader.references_error) == ("failed", references.FETCH_FAILED)
