import uuid

import pytest
from sqlalchemy import text, update

from app.core import papers
from app.core.chunking import ChunkDraft
from app.models import Paper

pytestmark = pytest.mark.anyio


async def upload(client, name="paper.pdf", data=b"%PDF-1.7\nbody"):
    return await client.post("/api/papers", files={"file": (name, data, "application/pdf")})


async def test_upload_creates_paper_and_enqueues_ingest(client, arq, pdf_dir):
    response = await upload(client, "Attention Is All You Need.pdf")

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Attention Is All You Need"
    assert body["status"] == "uploaded"
    assert arq.jobs == [("ingest_paper", body["id"])]
    assert (pdf_dir / f"{body['id']}.pdf").exists()


async def test_upload_non_pdf_is_rejected(client, arq, pdf_dir):
    response = await upload(client, "notes.txt", b"not a pdf")

    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]
    assert arq.jobs == []
    assert not pdf_dir.exists() or not any(pdf_dir.iterdir())


async def test_list_returns_newest_first(client, session):
    first = (await upload(client, "first.pdf")).json()
    second = (await upload(client, "second.pdf")).json()
    # The test transaction freezes now(), so both rows share created_at; age the first one.
    await session.execute(
        update(Paper).where(Paper.id == uuid.UUID(first["id"])).values(created_at=text("now() - interval '1 day'"))
    )

    ids = [p["id"] for p in (await client.get("/api/papers")).json()]
    assert ids.index(second["id"]) < ids.index(first["id"])


async def test_get_paper(client):
    created = (await upload(client)).json()

    response = await client.get(f"/api/papers/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize(("path", "status"), [(f"/api/papers/{uuid.uuid4()}", 404), ("/api/papers/not-a-uuid", 422)])
async def test_get_paper_errors(client, path, status):
    assert (await client.get(path)).status_code == status


async def test_chunks_filter_by_page(client, session):
    created = (await upload(client)).json()
    paper_id = uuid.UUID(created["id"])
    await papers.replace_chunks(
        session,
        paper_id,
        [
            ChunkDraft(ordinal=0, page=1, bbox=[[1, 2, 3, 4]], section_title=None, text="page one"),
            ChunkDraft(ordinal=1, page=2, bbox=[[1, 2, 3, 4], [5, 6, 7, 8]], section_title="Intro", text="page two"),
        ],
    )

    all_chunks = (await client.get(f"/api/papers/{paper_id}/chunks")).json()
    page_two = (await client.get(f"/api/papers/{paper_id}/chunks", params={"page": 2})).json()

    assert [c["ordinal"] for c in all_chunks] == [0, 1]
    assert [(c["text"], c["section_title"], c["bbox"]) for c in page_two] == [
        ("page two", "Intro", [[1, 2, 3, 4], [5, 6, 7, 8]])
    ]


async def test_chunks_of_unknown_paper_is_404(client):
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/chunks")).status_code == 404


async def test_reingest_enqueues_job(client, arq):
    created = (await upload(client)).json()
    arq.jobs.clear()

    response = await client.post(f"/api/papers/{created['id']}/reingest")

    assert response.status_code == 202
    assert arq.jobs == [("ingest_paper", created["id"])]


async def test_reingest_unknown_paper_is_404_and_enqueues_nothing(client, arq):
    response = await client.post(f"/api/papers/{uuid.uuid4()}/reingest")

    assert response.status_code == 404
    assert arq.jobs == []


async def test_health_vector_roundtrip(client):
    assert (await client.get("/api/health")).json() == {"orm_roundtrip": True, "raw_sql_nearest_is_self": True}
