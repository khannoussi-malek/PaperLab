"""Checking one claim against one paper needs the search to stay on that paper, and a paper's preprint and published
copies must not answer with the same passage twice."""

import uuid

import pytest

from app.core import library
from app.core.errors import InvalidInput, NotFound
from app.core.retrieval import RetrievedChunk
from app.models import Paper

pytestmark = pytest.mark.anyio


def text_of(n: int) -> str:
    return " ".join(f"word{n}{i}" for i in range(40))


def chunk(paper_id, text, distance=0.1, page=1):
    return RetrievedChunk(
        id=uuid.uuid4(), paper_id=paper_id, page=page, section=None, bbox=[], text=text, distance=distance
    )


async def papers_with(session, **fields):
    paper = Paper(title=fields.pop("title", f"P {uuid.uuid4().hex[:8]}"), status="ready", **fields)
    session.add(paper)
    await session.flush()
    return paper


@pytest.fixture
def retrieve(monkeypatch):
    calls = []
    answers = {"found": []}

    async def fake_searchable(_session, _scope, embedder):
        return embedder

    async def fake_retrieve(_session, _query, **kwargs):
        calls.append(kwargs)
        return answers["found"]

    monkeypatch.setattr(library, "searchable", fake_searchable)
    monkeypatch.setattr(library, "retrieve", fake_retrieve)
    return calls, answers


async def test_a_paper_id_keeps_the_search_on_that_paper_and_lifts_the_per_paper_limit(session, retrieve):
    calls, answers = retrieve
    paper = await papers_with(session)
    answers["found"] = [chunk(paper.id, text_of(i), page=i + 1) for i in range(5)]
    out = await library.search(session, "q", paper_id=paper.id, limit=5)
    assert [p.page for p in out] == [1, 2, 3, 4, 5]
    assert calls[0]["paper_ids"] == [paper.id] and calls[0]["per_paper"] >= 5 and calls[0]["k"] >= 5


async def test_a_doi_finds_the_paper(session, retrieve):
    calls, _ = retrieve
    paper = await papers_with(session, doi=f"10.1/{uuid.uuid4().hex[:8]}")
    await library.search(session, "q", doi=paper.doi.upper())
    assert calls[0]["paper_ids"] == [paper.id]


async def test_a_doi_the_library_does_not_hold_says_so(session, retrieve):
    with pytest.raises(NotFound, match="paper_not_in_library"):
        await library.search(session, "q", doi="10.1/none")


async def test_a_paper_id_and_a_doi_together_are_refused(session, retrieve):
    with pytest.raises(InvalidInput, match="paper_or_doi"):
        await library.search(session, "q", paper_id=uuid.uuid4(), doi="10.1/x")


@pytest.mark.parametrize("limit", [0, -1, 51])
async def test_a_limit_out_of_range_is_refused(session, retrieve, limit):
    with pytest.raises(InvalidInput, match="invalid_limit"):
        await library.search(session, "q", limit=limit)


async def test_a_limit_caps_the_answer(session, retrieve):
    _, answers = retrieve
    paper = await papers_with(session)
    answers["found"] = [chunk(paper.id, text_of(i)) for i in range(5)]
    assert len(await library.search(session, "q", limit=2)) == 2


async def test_the_same_passage_from_a_preprint_and_its_published_copy_comes_once(session, retrieve):
    _, answers = retrieve
    published = await papers_with(session, doi=f"10.1/{uuid.uuid4().hex[:8]}", title="A study of creativity")
    preprint = await papers_with(session, title="A study of creativity: extended", published_doi=published.doi)
    same = text_of(1)
    answers["found"] = [chunk(preprint.id, same, 0.1), chunk(published.id, same + " extra", 0.11)]
    out = await library.search(session, "q")
    assert [p.paper_id for p in out] == [preprint.id]
    assert out[0].also_in == [published.id]


async def test_copies_with_different_passages_both_stay(session, retrieve):
    _, answers = retrieve
    published = await papers_with(session, doi=f"10.1/{uuid.uuid4().hex[:8]}")
    preprint = await papers_with(session, published_doi=published.doi)
    answers["found"] = [chunk(preprint.id, text_of(1)), chunk(published.id, text_of(2))]
    assert {p.paper_id for p in await library.search(session, "q")} == {preprint.id, published.id}


async def test_the_same_words_in_unrelated_papers_both_stay(session, retrieve):
    _, answers = retrieve
    one, two = await papers_with(session), await papers_with(session)
    answers["found"] = [chunk(one.id, text_of(1)), chunk(two.id, text_of(1))]
    assert len(await library.search(session, "q")) == 2


async def test_copies_with_one_title_collapse_without_a_published_doi(session, retrieve):
    _, answers = retrieve
    one = await papers_with(session, title="The same title", year=2024)
    two = await papers_with(session, title="The  same title.", year=2025)
    answers["found"] = [chunk(one.id, text_of(1)), chunk(two.id, text_of(1))]
    assert [p.paper_id for p in await library.search(session, "q")] == [one.id]
