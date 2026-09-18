"""The whole library's graph: one link per pair per kind, derived from the shared edge definition (M7, D106)."""

import uuid

import pytest
from sqlalchemy import insert

from app.core import graph, paper_links, workspaces
from app.core.errors import NotFound
from app.models import (
    Author,
    Chunk,
    ExternalRef,
    Note,
    Paper,
    note_anchors,
    paper_authors,
    paper_references,
    paper_topics,
)
from tests.conftest import unit_vector

pytestmark = pytest.mark.anyio

# The dev database (D15) holds the owner's papers, so every fixture carries the run and every assertion counts only
# this test's own papers.
RUN = uuid.uuid4().hex[:8]


async def add_papers(session, *titles: str, **fields) -> list[Paper]:
    papers = [Paper(title=title, file_path="/nonexistent.pdf", year=2020, **fields) for title in titles]
    session.add_all(papers)
    await session.commit()
    return papers


async def chunked(session, paper: Paper, seed: str) -> None:
    """One chunk with a known vector, so the paper has an average to compare."""
    session.add(
        Chunk(
            paper_id=paper.id,
            ordinal=0,
            page=1,
            bbox=[[0, 0, 1, 1]],
            text=seed,
            embedding=unit_vector(f"{RUN}-{seed}"),
            embed_model="test",
            strategy_ver=1,
        )
    )
    await session.commit()


# Undirected kinds are emitted once per pair, with the smaller id first, so their titles come back in no fixed
# order; `cites` and `manual` keep the direction they were drawn in.
DIRECTED = ("cites", "manual")


def links_between(result: "graph.Graph", papers: list[Paper]) -> list[tuple[str, str, str]]:
    """This test's own links, as sorted (kind, one title, the other). A list, so a pair emitted twice shows up."""
    title = {paper.id: paper.title for paper in papers}
    mine = [link for link in result.links if link.source in title and link.target in title]
    return sorted(
        (link.kind, title[link.source], title[link.target])
        if link.kind in DIRECTED
        else (link.kind, *sorted((title[link.source], title[link.target])))
        for link in mine
    )


async def test_every_kind_appears_once_per_pair_and_cites_keeps_its_direction(session):
    mate, noted, coauthor, topical, cited, drawn = await add_papers(
        session, "Mate", "Noted", "Coauthor", "Topical", "Cited", "Drawn"
    )
    mine = [mate, noted, coauthor, topical, cited, drawn]
    workspace = await workspaces.create(session, f"Graph {RUN}")
    for paper in (mate, noted):
        await workspaces.add_paper(session, workspace.id, paper.id)
    note = Note(body="one note on two papers", provenance="human")
    session.add(note)
    await session.flush()
    await session.execute(insert(note_anchors), [
        {"note_id": note.id, "paper_id": paper.id, "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}
        for paper in (noted, coauthor)
    ])  # fmt: skip
    author = Author(openalex_id=f"A-m7-{RUN}", display_name="Ada Lovelace")
    session.add(author)
    await session.flush()
    await session.execute(insert(paper_authors), [
        {"paper_id": paper.id, "author_id": author.id, "position": 1} for paper in (coauthor, topical)
    ])  # fmt: skip
    ref = ExternalRef(title="cited", imported_as=cited.id)
    session.add(ref)
    await session.flush()
    await session.execute(
        insert(paper_references), [{"paper_id": topical.id, "ref_id": ref.id, "direction": "cites", "position": 0}]
    )
    await paper_links.create(session, drawn.id, mate.id, "builds on")
    await session.commit()

    result = await graph.library_graph(session)

    assert links_between(result, mine) == [
        ("cites", "Topical", "Cited"),
        ("co_anchored", "Coauthor", "Noted"),
        ("co_authored", "Coauthor", "Topical"),
        ("manual", "Drawn", "Mate"),
        ("same_workspace", "Mate", "Noted"),
    ]
    assert result.truncated is False


async def test_shared_topics_ignore_case_and_link_a_pair_once(session):
    left, right = await add_papers(session, "Left", "Right")
    await session.execute(insert(paper_topics), [
        {"paper_id": left.id, "source": "author", "label": f"Retrieval {RUN}"},
        {"paper_id": right.id, "source": "openalex", "label": f"retrieval {RUN}"},
    ])  # fmt: skip
    await session.commit()

    result = await graph.library_graph(session)

    assert links_between(result, [left, right]) == [("shares_topic", "Left", "Right")]


async def test_similar_links_each_paper_to_its_three_nearest_and_a_paper_with_no_chunks_has_none(session):
    papers = await add_papers(session, *[f"S{n} {RUN}" for n in range(6)])
    alone, *rest = papers
    # Five vectors on a line: S1's three nearest are S2, S3, S4 — never S5.
    axis = unit_vector(f"{RUN}-axis")
    other = unit_vector(f"{RUN}-other")
    for step, paper in enumerate(rest):
        vector = [a + step * 0.35 * o for a, o in zip(axis, other, strict=True)]
        session.add(
            Chunk(
                paper_id=paper.id,
                ordinal=0,
                page=1,
                bbox=[[0, 0, 1, 1]],
                text=paper.title,
                embedding=vector,
                embed_model="test",
                strategy_ver=1,
            )
        )
    await session.commit()

    result = await graph.library_graph(session)
    similar = {frozenset(pair) for kind, *pair in links_between(result, papers) if kind == "similar"}

    first, second, third, fourth, fifth = (paper.title for paper in rest)
    assert frozenset((first, second)) in similar
    assert frozenset((first, third)) in similar
    assert frozenset((first, fourth)) in similar
    assert frozenset((first, fifth)) not in similar
    assert not [pair for pair in similar if alone.title in pair]


async def test_a_workspace_returns_only_its_papers_and_the_links_between_them(session):
    inside_a, inside_b, outside = await add_papers(session, f"In A {RUN}", f"In B {RUN}", f"Out {RUN}")
    workspace = await workspaces.create(session, f"Only {RUN}")
    for paper in (inside_a, inside_b):
        await workspaces.add_paper(session, workspace.id, paper.id)
    await paper_links.create(session, inside_a.id, outside.id, "left the workspace")
    await session.commit()

    result = await graph.library_graph(session, workspace.id)

    assert [node.title for node in result.nodes] == [inside_a.title, inside_b.title]
    assert links_between(result, [inside_a, inside_b, outside]) == [
        ("same_workspace", inside_a.title, inside_b.title)
    ]
    with pytest.raises(NotFound):
        await graph.library_graph(session, uuid.uuid4())


async def test_a_paper_with_no_link_is_still_a_node_and_carries_its_workspaces_notes_and_status(session):
    (lonely,) = await add_papers(session, f"Lonely {RUN}", status="ready")
    workspace = await workspaces.create(session, f"Home {RUN}")
    await workspaces.add_paper(session, workspace.id, lonely.id)
    note = Note(body="a note", provenance="human")
    session.add(note)
    await session.flush()
    await session.execute(
        insert(note_anchors),
        [{"note_id": note.id, "paper_id": lonely.id, "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}],
    )
    await session.commit()

    result = await graph.library_graph(session)

    node = next(node for node in result.nodes if node.id == lonely.id)
    assert (node.title, node.workspaces, node.has_notes, node.status) == (
        lonely.title,
        [f"Home {RUN}"],
        True,
        "ready",
    )
    assert not [link for link in result.links if lonely.id in (link.source, link.target)]


async def test_truncated_flips_at_max_links_and_every_kind_survives_the_cap(session, monkeypatch):
    # A workspace of 8 papers draws 28 same_workspace links; one drawn link and one citation must still come back.
    crowd = await add_papers(session, *[f"Crowd {n} {RUN}" for n in range(8)])
    workspace = await workspaces.create(session, f"Crowd {RUN}")
    for paper in crowd:
        await workspaces.add_paper(session, workspace.id, paper.id)
    ref = ExternalRef(title="cited", imported_as=crowd[0].id)
    session.add(ref)
    await session.flush()
    await session.execute(
        insert(paper_references), [{"paper_id": crowd[1].id, "ref_id": ref.id, "direction": "cites", "position": 0}]
    )
    await paper_links.create(session, crowd[2].id, crowd[3].id, "builds on")
    await session.commit()
    monkeypatch.setattr(graph, "MAX_LINKS", 6)

    result = await graph.library_graph(session, workspace.id)

    assert result.truncated is True
    assert len(result.links) == 6
    assert {link.kind for link in result.links} == {"same_workspace", "cites", "manual"}


async def test_similar_never_compares_vectors_from_another_embedding_model(session):
    # Mid-reindex, one paper's chunks still carry the old model's vectors. `stale` holds exactly the same vector as
    # the other two, so if models were mixed it would be the nearest paper to both.
    same, twin, stale = await add_papers(session, *[f"M{n} {RUN}" for n in range(3)])
    vector = unit_vector(f"{RUN}-model")
    for paper, model in [(same, "test"), (twin, "test"), (stale, "an-older-model")]:
        session.add(
            Chunk(
                paper_id=paper.id,
                ordinal=0,
                page=1,
                bbox=[[0, 0, 1, 1]],
                text=paper.title,
                embedding=vector,
                embed_model=model,
                strategy_ver=1,
            )
        )
    await session.commit()

    result = await graph.library_graph(session)
    similar = {frozenset(pair) for kind, *pair in links_between(result, [same, twin, stale]) if kind == "similar"}

    assert frozenset((same.title, twin.title)) in similar
    assert not [pair for pair in similar if stale.title in pair]


async def test_related_walks_similar_and_manual_links_as_well(session):
    # related() reads the same edge definition as the graph (D106), so the MCP tool sees these two kinds too.
    near, close, drawn = await add_papers(session, *[f"R{n} {RUN}" for n in range(3)])
    for paper in (near, close):
        await chunked(session, paper, "related")  # the same vector: each is the other's nearest
    await paper_links.create(session, near.id, drawn.id, f"builds on {RUN}")

    via = {row.title: row.via for row in await graph.related(session, near.id, hops=1)}

    assert "similar" in via[close.title]
    assert via[drawn.title] == ["manual"]
