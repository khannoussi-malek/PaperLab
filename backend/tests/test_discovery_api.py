import uuid
from contextlib import aclosing
from dataclasses import replace

import pytest
from conftest import recorded_discovery
from sqlalchemy import delete

from app.api.deps import get_discovery
from app.config import settings
from app.core import discovery, paper_sources
from app.models import Paper, PaperSources
from app.providers import discovery_fake

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7\n%a found paper\n"


@pytest.fixture
def discovery_api(app, discovery_fakes):
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers
    return discovery_fakes


def body(**candidate) -> dict:
    return {"candidate": {"title": "Found Paper", "doi": "10.5555/m19-api", **candidate}}


async def test_search_returns_candidates(client, discovery_api):
    discovery_api.openalex.route("/works", recorded_discovery("openalex_search_bert"))
    discovery_api.s2.reply("/graph/v1/paper/batch", 200, json=recorded_discovery("s2_batch_bert")[:1])

    response = await client.get("/api/discovery/search", params={"q": "BERT"})

    assert response.status_code == 200
    assert response.json()["notices"] == []
    bert = response.json()["results"][0]
    assert bert["sources"] == ["openalex"]
    assert (bert["openalex_id"], bert["arxiv_id"], bert["paper_id"]) == ("W2963341956", "1810.04805", None)
    assert bert["pdf_urls"][0] == "https://arxiv.org/pdf/1810.04805"


@pytest.mark.parametrize(("q", "status"), [("   ", 422), ("x" * 501, 422)], ids=["blank", "too-long"])
async def test_search_rejects_a_blank_or_huge_query(client, discovery_api, q, status):
    response = await client.get("/api/discovery/search", params={"q": q})

    assert response.status_code == status
    assert discovery_api.openalex.requests == []


async def test_search_says_no_source_that_is_on_can_answer(app, client, discovery_api):
    app.dependency_overrides[get_discovery] = lambda: replace(discovery_api.providers, openalex=None)

    response = await client.get("/api/discovery/search", params={"q": "BERT"})

    assert response.status_code == 409
    assert response.json()["detail"].startswith("No paper source that can look this up is on")


async def test_similar_says_semantic_scholar_is_off(app, client, discovery_api, session):
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", doi="10.18653/v1/n19-1423")
    session.add(paper)
    await session.flush()
    app.dependency_overrides[get_discovery] = lambda: replace(discovery_api.providers, s2=None)

    response = await client.get(f"/api/papers/{paper.id}/similar")

    assert (response.status_code, response.json()["detail"]) == (409, discovery.S2_OFF)


async def test_similar_lists_suggestions_for_a_library_paper(client, discovery_api, session):
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", doi="10.18653/v1/n19-1423")
    session.add(paper)
    await session.flush()
    discovery_api.s2.reply(
        "/recommendations/v1/papers/forpaper/DOI:10.18653/v1/n19-1423",
        200,
        json=recorded_discovery("s2_recommend_bert"),
    )

    response = await client.get(f"/api/papers/{paper.id}/similar")

    assert response.status_code == 200
    assert len(response.json()) == len(recorded_discovery("s2_recommend_bert")["recommendedPapers"])


async def test_similar_for_an_unknown_paper_is_404(client, discovery_api):
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/similar")).status_code == 404


async def test_similar_says_semantic_scholar_is_busy(client, discovery_api, session):
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", doi="10.5555/m19-busy")
    session.add(paper)
    await session.flush()
    discovery_api.s2.reply("/recommendations/v1/papers/forpaper/DOI:10.5555/m19-busy", 429, json={"code": "429"})

    response = await client.get(f"/api/papers/{paper.id}/similar")

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Semantic Scholar is busy")


async def test_add_downloads_files_in_the_workspace_and_enqueues_ingest(client, discovery_api, arq, pdf_dir):
    discovery_api.pdf_host.reply("/copy.pdf", 200, content=PDF)
    workspace = (await client.post("/api/workspaces", json={"name": f"M19 {uuid.uuid4().hex[:8]}"})).json()

    response = await client.post(
        "/api/discovery/add",
        json={
            **body(pdf_urls=["https://pdf.example/copy.pdf"], paper_id=str(uuid.uuid4())),
            "workspace_id": workspace["id"],
        },
    )

    assert response.status_code == 201
    paper = response.json()
    assert (paper["title"], paper["doi"], paper["status"]) == ("Found Paper", "10.5555/m19-api", "uploaded")
    assert paper["workspace_ids"] == [workspace["id"]]
    assert arq.jobs == [("ingest_paper", paper["id"])]
    assert (pdf_dir / f"{paper['id']}.pdf").read_bytes() == PDF


async def test_add_to_an_unknown_workspace_is_404_before_any_download(client, discovery_api, arq):
    response = await client.post(
        "/api/discovery/add",
        json={**body(pdf_urls=["https://pdf.example/copy.pdf"]), "workspace_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
    assert discovery_api.pdf_host.requests == []
    assert arq.jobs == []


async def test_add_without_a_free_pdf_is_409_and_enqueues_nothing(client, discovery_api, arq):
    discovery_api.pdf_host.reply("/landing", 200, text="<html>landing</html>")

    response = await client.post("/api/discovery/add", json=body(pdf_urls=["https://pdf.example/landing"]))

    assert response.status_code == 409
    assert response.json()["detail"].startswith("No free PDF was found")
    assert arq.jobs == []


async def test_add_a_paper_already_in_the_library_is_409(client, discovery_api, session, arq):
    session.add(Paper(title="Owned", file_path="/nonexistent.pdf", doi="10.5555/m19-api"))
    await session.flush()

    response = await client.post("/api/discovery/add", json=body(pdf_urls=["https://pdf.example/copy.pdf"]))

    assert response.status_code == 409
    assert response.json()["detail"] == "This paper is already in your library."


@pytest.mark.parametrize(
    "candidate",
    [
        {"pdf_urls": ["file:///etc/passwd"]},
        {"pdf_urls": [f"https://pdf.example/{i}.pdf" for i in range(11)]},
        {"doi": "not-a-doi"},
        {"arxiv_id": "1810.04805v2"},
        {"s2_id": "short"},
        {"title": ""},
    ],
    ids=["non-http-url", "eleven-urls", "bad-doi", "versioned-arxiv-id", "bad-s2-id", "empty-title"],
)
async def test_add_rejects_a_malformed_candidate(client, discovery_api, candidate):
    response = await client.post("/api/discovery/add", json=body(**candidate))

    assert response.status_code == 422
    assert discovery_api.pdf_host.requests == []


@pytest.fixture
async def no_sources_row(session):
    # The dev database (D15) holds the owner's own row; hide it inside the test's rolled-back transaction.
    await session.execute(delete(PaperSources))
    return session


async def test_the_discovery_dependency_serves_the_fake_offline_and_closes_its_clients(monkeypatch, no_sources_row):
    monkeypatch.setattr(settings, "discovery_provider", "fake")
    await paper_sources.update(no_sources_row, {"api_keys": {"semantic_scholar": "secret-key"}})

    async with aclosing(get_discovery(no_sources_row)) as dependency:
        providers = await anext(dependency)
        assert providers.openalex is None  # off by default, fake or not
        assert providers.s2.headers["x-api-key"] == "secret-key"
        assert providers.unpaywall.params["email"] == discovery_fake.MAILTO  # the fake stands in for the email
        assert (await providers.pdf.get(f"{discovery_fake.PDF_HOST}/paper.pdf")).content.startswith(b"%PDF")

    assert providers.s2.is_closed and providers.pdf.is_closed and providers.unpaywall.is_closed


async def test_the_live_discovery_dependency_follows_settings(no_sources_row):
    await paper_sources.update(no_sources_row, {"contact_email": "me@example.org", "enabled": {"crossref": False}})

    async with aclosing(get_discovery(no_sources_row)) as dependency:
        providers = await anext(dependency)
        assert (providers.openalex, providers.crossref) == (None, None)
        assert providers.unpaywall.params["email"] == "me@example.org"
        assert "x-api-key" not in providers.s2.headers
