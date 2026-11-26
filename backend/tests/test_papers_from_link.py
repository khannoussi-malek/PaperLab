"""POST /api/papers/from-link: a paper from a link to its PDF, as Quick Capture sends one dragged or copied from a
browser. The download itself is the add pipeline's (tested with it); here, what the endpoint answers."""

import pytest

from app.core.papers import pipeline_add
from app.domain.errors import InvalidInput
from app.models import Paper

pytestmark = pytest.mark.anyio

LINK = "https://example.org/papers/attention.pdf"


async def test_a_pdf_link_gives_the_new_paper(client, session, monkeypatch):
    paper = Paper(title="attention.pdf", file_path="/attention.pdf")
    session.add(paper)
    await session.flush()
    asked = []

    async def add(_session, identifier, workspace=None, save_without_pdf=False):
        asked.append(identifier)
        return pipeline_add.AddPaperResult(status="queued", paper_id=paper.id, title=paper.title)

    monkeypatch.setattr(pipeline_add, "add_paper", add)
    response = await client.post("/api/papers/from-link", json={"link": f"  {LINK} "})
    assert response.status_code == 201, response.text
    assert (response.json()["id"], asked) == (str(paper.id), [LINK])


async def test_no_pdf_at_the_link_or_a_private_address_says_why(client, monkeypatch):
    async def nothing(*_args, **_kwargs):
        return pipeline_add.AddPaperResult(status="no_free_pdf")

    monkeypatch.setattr(pipeline_add, "add_paper", nothing)
    response = await client.post("/api/papers/from-link", json={"link": LINK})
    assert (response.status_code, response.json()["detail"]) == (409, pipeline_add_sentence("NO_PDF_AT_LINK"))

    async def unsafe(*_args, **_kwargs):
        raise InvalidInput("unsafe_url", url=LINK)

    monkeypatch.setattr(pipeline_add, "add_paper", unsafe)
    response = await client.post("/api/papers/from-link", json={"link": "http://192.168.1.4/a.pdf"})
    assert (response.status_code, response.json()["detail"]) == (409, pipeline_add_sentence("PRIVATE_LINK"))


async def test_only_a_web_link_is_taken(client):
    for link in ("ftp://example.org/a.pdf", "attention is all you need", "https://"):
        assert (await client.post("/api/papers/from-link", json={"link": link})).status_code == 422, link


def pipeline_add_sentence(name: str) -> str:
    from app.api import papers as api

    return getattr(api, name)
