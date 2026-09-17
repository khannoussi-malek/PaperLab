"""Related papers, derived from the tables that already hold each link (M6, D88). Needs M7.5's migration 0010."""

import uuid

import pytest
from sqlalchemy import insert

from app.core import graph, workspaces
from app.core.errors import InvalidInput, NotFound
from app.models import Author, ExternalRef, Note, Paper, note_anchors, paper_authors, paper_references, paper_topics

pytestmark = pytest.mark.anyio

# The dev database (D15) holds the owner's papers, topics and references: every name, label and identifier here carries
# the run, so nothing of theirs can link to these papers.
RUN = uuid.uuid4().hex[:8]


async def add_papers(session, *titles: str, **fields) -> list[Paper]:
    papers = [Paper(title=title, file_path="/nonexistent.pdf", year=2020, **fields) for title in titles]
    session.add_all(papers)
    await session.commit()
    return papers


async def same_workspace(session, *papers: Paper) -> None:
    workspace = await workspaces.create(session, f"Graph {uuid.uuid4().hex[:8]}")
    for paper in papers:
        await workspaces.add_paper(session, workspace.id, paper.id)


def listed(related: list[graph.Related]) -> list[tuple[str, int, list[str]]]:
    return [(r.title, r.hops, r.via) for r in related]


async def test_hops_one_two_and_three_reach_exactly_the_right_papers(session):
    a, b, c, d = await add_papers(session, "A", "B", "C", "D")
    await same_workspace(session, a, b)
    await same_workspace(session, b, c)
    await same_workspace(session, c, d)

    one = await graph.related(session, a.id, hops=1)
    two = await graph.related(session, a.id, hops=2)
    three = await graph.related(session, a.id, hops=3)

    assert listed(one) == [("B", 1, ["same_workspace"])]
    assert listed(two) == [("B", 1, ["same_workspace"]), ("C", 2, ["same_workspace"])]
    assert [(r.paper_id, r.hops) for r in three] == [(b.id, 1), (c.id, 2), (d.id, 3)]


async def test_a_cycle_ends_and_each_paper_is_reported_at_its_nearest_distance(session):
    a, b, c = await add_papers(session, "A", "B", "C")
    await same_workspace(session, a, b)
    await same_workspace(session, b, c)
    await same_workspace(session, c, a)

    related = await graph.related(session, a.id, hops=3)

    assert listed(related) == [("B", 1, ["same_workspace"]), ("C", 1, ["same_workspace"])]


async def test_each_kind_of_link(session):
    (me,) = await add_papers(session, "Me", doi=f"10.5555/m6-me-{RUN}")
    mate, noted, coauthor, topical, both = await add_papers(session, "Mate", "Noted", "Coauthor", "Topical", "Both")
    (imported,) = await add_papers(session, "Imported")
    await add_papers(session, "DOI match", doi=f"10.5555/m6-cited-{RUN}")
    await add_papers(session, "OpenAlex match", openalex_id=f"W-m6-{RUN}")
    await add_papers(session, "Preprint match", doi=f"10.48550/arxiv.{RUN}.00001")
    (citer,) = await add_papers(session, "Citer")
    await same_workspace(session, me, mate)
    await same_workspace(session, me, both)
    note = Note(body="links two papers", provenance="human")
    session.add(note)
    await session.flush()
    await session.execute(insert(note_anchors), [
        {"note_id": note.id, "paper_id": paper.id, "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}
        for paper in (me, noted)
    ])  # fmt: skip
    author = Author(openalex_id=f"A-m6-{RUN}", display_name="Ada Lovelace")
    session.add(author)
    await session.flush()
    await session.execute(insert(paper_authors), [
        {"paper_id": paper.id, "author_id": author.id, "position": 1} for paper in (me, coauthor)
    ])  # fmt: skip
    await session.execute(insert(paper_topics), [
        {"paper_id": me.id, "source": "author", "label": f"Retrieval {RUN}"},
        {"paper_id": topical.id, "source": "openalex", "label": f"retrieval {RUN}"},
        {"paper_id": both.id, "source": "author", "label": f"Retrieval {RUN}"},
    ])  # fmt: skip
    refs = [
        ExternalRef(title="imported", imported_as=imported.id),
        ExternalRef(title="matched by DOI", doi=f"10.5555/M6-CITED-{RUN}"),
        ExternalRef(title="matched by OpenAlex", openalex_id=f"W-m6-{RUN}"),
        ExternalRef(title="matched by arXiv", arxiv_id=f"{RUN}.00001"),
        ExternalRef(title="me, as the citer lists me", doi=f"10.5555/m6-me-{RUN}"),
        ExternalRef(title="not in the library", doi=f"10.5555/m6-elsewhere-{RUN}"),
    ]
    session.add_all(refs)
    await session.flush()
    await session.execute(insert(paper_references), [
        {"paper_id": me.id, "ref_id": refs[0].id, "direction": "cites", "position": 0},
        {"paper_id": me.id, "ref_id": refs[1].id, "direction": "cites", "position": 1},
        {"paper_id": me.id, "ref_id": refs[2].id, "direction": "cited_by", "position": 0},
        {"paper_id": me.id, "ref_id": refs[3].id, "direction": "cited_by", "position": 1},
        {"paper_id": me.id, "ref_id": refs[5].id, "direction": "cites", "position": 2},
        {"paper_id": citer.id, "ref_id": refs[4].id, "direction": "cites", "position": 0},
    ])  # fmt: skip
    await session.commit()

    related = await graph.related(session, me.id)

    assert listed(related) == [
        ("Both", 1, ["same_workspace", "shares_topic"]),
        ("Citer", 1, ["cited_by"]),
        ("Coauthor", 1, ["co_authored"]),
        ("DOI match", 1, ["cites"]),
        ("Imported", 1, ["cites"]),
        ("Mate", 1, ["same_workspace"]),
        ("Noted", 1, ["co_anchored"]),
        ("OpenAlex match", 1, ["cited_by"]),
        ("Preprint match", 1, ["cited_by"]),
        ("Topical", 1, ["shares_topic"]),
    ]
    assert listed(await graph.related(session, imported.id)) == [("Me", 1, ["cited_by"])]


async def test_hops_must_be_one_to_three_and_the_paper_must_exist(session):
    (paper,) = await add_papers(session, "Alone")

    for hops in (0, 4):
        with pytest.raises(InvalidInput, match="^hops_out_of_range$") as refused:
            await graph.related(session, paper.id, hops=hops)
        assert refused.value.details == {"allowed": [1, 3]}
    with pytest.raises(NotFound):
        await graph.related(session, uuid.uuid4())
    assert await graph.related(session, paper.id) == []
