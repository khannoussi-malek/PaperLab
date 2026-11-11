import uuid

import pytest
from pdf_papers import chunked_paper

from app.core import library, novelty, workspaces
from app.core.errors import InvalidInput, NotFound

pytestmark = pytest.mark.anyio


def passage(paper_id, distance, title="T", page=1, text="x", abstract=False):
    return library.Passage(
        chunk_id=uuid.uuid4(), paper_id=paper_id, paper_title=title, year=2020, page=None if abstract else page,
        section="S", text=text, distance=distance, source_type=None, peer_reviewed="unknown", published_venue=None,
        evidence_access="full_text", from_abstract=abstract,
    )


@pytest.fixture
def found(monkeypatch):
    """What library.search answers; records its arguments."""
    state = {"passages": [], "calls": []}

    async def fake(session, query, workspace=None, *, limit, **kw):
        state["calls"].append((query, workspace, limit))
        return state["passages"]

    monkeypatch.setattr(library, "search", fake)

    async def count(session, workspace):
        return 7

    monkeypatch.setattr(novelty, "_searched", count)
    return state


async def test_keeps_each_papers_closest_passage_and_orders_by_it(session, found):
    a, b = uuid.uuid4(), uuid.uuid4()
    found["passages"] = [passage(a, 0.5, text="far a"), passage(b, 0.3, text="b"), passage(a, 0.2, text="near a")]
    report = await novelty.check(session, "idea")
    assert [(p.paper_id, p.passage) for p in report.papers] == [(a, "near a"), (b, "b")]


async def test_at_most_ten_papers(session, found):
    found["passages"] = [passage(uuid.uuid4(), i / 100) for i in range(15)]
    assert len((await novelty.check(session, "idea")).papers) == 10


@pytest.mark.parametrize(
    ("distance", "label"),
    [
        (0.0, "very close"),
        (0.25, "very close"),
        (0.26, "related"),
        (0.45, "related"),
        (0.46, "distant"),
        (2, "distant"),
    ],
)
async def test_label_cuts(session, found, distance, label):
    found["passages"] = [passage(uuid.uuid4(), distance)]
    assert (await novelty.check(session, "idea")).papers[0].label == label


async def test_an_abstract_has_no_page(session, found):
    found["passages"] = [passage(uuid.uuid4(), 0.1, abstract=True)]
    hit = (await novelty.check(session, "idea")).papers[0]
    assert hit.page is None and hit.from_abstract


async def test_the_note_is_always_there_even_with_nothing_found(session, found):
    report = await novelty.check(session, "idea")
    assert report.papers == [] and report.searched_papers == 7
    assert "only covers your own library (7 papers searched)" in report.note


async def test_passes_text_workspace_and_the_largest_limit_on(session, found):
    await novelty.check(session, "  idea  ", "Ws")
    assert found["calls"] == [("idea", "Ws", library.MAX_LIMIT)]


async def test_too_long_text_is_refused_before_searching(session, found):
    with pytest.raises(InvalidInput) as caught:
        await novelty.check(session, "x" * (novelty.MAX_CHARS + 1))
    assert str(caught.value) == "text_too_long" and found["calls"] == []


async def test_empty_text_is_refused_by_the_search(session):
    with pytest.raises(InvalidInput):
        await novelty.check(session, "   ")


async def test_unknown_workspace_is_not_found(session, embedder):
    with pytest.raises(NotFound):
        await novelty.check(session, "idea", "No such workspace", embedder=embedder)


async def test_real_search_close_paper_is_very_close_and_orthogonal_one_distant(session, tmp_path, embedder):
    near, _, near_vectors = await chunked_paper(session, tmp_path / "a", title="Near paper")
    far, _, _ = await chunked_paper(session, tmp_path / "b", title="Far paper")
    ws = await workspaces.create(session, f"Novelty {uuid.uuid4().hex[:6]}")
    for paper in (near, far):
        await workspaces.add_paper(session, ws.id, paper.id)
    embedder.vectors["search_query: my idea"] = near_vectors[0]
    report = await novelty.check(session, "my idea", ws.name, embedder=embedder)
    assert report.searched_papers == 2
    assert report.papers[0].title == "Near paper" and report.papers[0].label == "very close"
    assert report.papers[0].page == 1
    assert {p.label for p in report.papers[1:]} <= {"related", "distant"}


async def test_an_abstract_passage_drops_the_abstract_only_prefix(session, found):
    found["passages"] = [passage(uuid.uuid4(), 0.1, text="(abstract only) An abstract line.", abstract=True)]
    hit = (await novelty.check(session, "idea")).papers[0]
    assert hit.passage == "An abstract line." and hit.from_abstract
