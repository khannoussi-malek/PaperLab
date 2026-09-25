"""Search and the paper card, as the MCP tools return them (M6)."""

import uuid
from collections import Counter

import numpy as np
import pytest
from conftest import unit_vector
from pdf_papers import TWO_LINE_QUOTE, chunked_paper
from sqlalchemy import delete
from test_note_papers import paper_only_note

from app.core import library, notes, workspaces
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Chunk, Paper, Provenance

pytestmark = pytest.mark.anyio

QUESTION = "how are notes anchored?"
RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)


@pytest.fixture
async def only_test_chunks(session):
    """The dev database (D15) holds the owner's chunks, embedded with a real model rather than the tests' "test":
    a library-wide search would refuse them. Hide them inside this test's rolled-back transaction."""
    await session.execute(delete(Chunk))
    return session


def planted_query(embedder) -> list[float]:
    """A query vector no earlier run used (D37), returned for QUESTION."""
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {QUESTION}"] = query
    return query


def at_spread(query: list[float], spread: float) -> list[float]:
    """A unit vector at cosine distance 1 - 1/sqrt(1 + spread²) from the query: a larger spread is farther."""
    q = np.array(query)
    noise = np.array(unit_vector(uuid.uuid4().hex))
    noise -= noise.dot(q) * q
    vector = q + spread * noise / np.linalg.norm(noise)
    return (vector / np.linalg.norm(vector)).tolist()


async def paper_near(session, query, title: str, spreads: list[float], model: str = "test") -> Paper:
    """A ready paper whose chunk i sits at spreads[i] from the query, on page i + 1."""
    paper = Paper(title=title, year=2021, file_path="/nonexistent.pdf", status="ready", page_count=len(spreads))
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]],
            section_title="Method" if i else None, text=f"{title} passage {i}",
            embedding=at_spread(query, spread), embed_model=model, strategy_ver=1,
        )  # fmt: skip
        for i, spread in enumerate(spreads)
    )
    await session.commit()
    return paper


async def test_search_returns_passages_closest_first_with_their_paper(only_test_chunks, embedder):
    session = only_test_chunks
    query = planted_query(embedder)
    near = await paper_near(session, query, "Near", [0.1, 0.4])
    far = await paper_near(session, query, "Far", [0.2])

    passages = await library.search(session, QUESTION, embedder=embedder)

    assert [(p.paper_title, p.page, p.section, p.text) for p in passages] == [
        ("Near", 1, None, "Near passage 0"),
        ("Far", 1, None, "Far passage 0"),
        ("Near", 2, "Method", "Near passage 1"),
    ]
    assert [p.paper_id for p in passages] == [near.id, far.id, near.id]
    assert all(isinstance(p.chunk_id, uuid.UUID) and p.year == 2021 for p in passages)
    assert [p.distance for p in passages] == sorted(p.distance for p in passages)


async def test_search_keeps_at_most_three_passages_from_one_paper(only_test_chunks, embedder):
    session = only_test_chunks
    query = planted_query(embedder)
    await paper_near(session, query, "Verbose", [0.1, 0.11, 0.12, 0.13, 0.14, 0.15])
    await paper_near(session, query, "Brief", [0.5, 0.6])

    passages = await library.search(session, QUESTION, embedder=embedder)

    assert Counter(p.paper_title for p in passages) == {"Verbose": 3, "Brief": 2}


async def test_search_in_a_workspace_sees_only_its_papers(session, embedder):
    query = planted_query(embedder)
    await paper_near(session, query, "Outside", [0.05])
    inside = await paper_near(session, query, "Inside", [0.3])
    workspace = await workspaces.create(session, f"Search scope {RUN}")
    await workspaces.add_paper(session, workspace.id, inside.id)

    passages = await library.search(session, QUESTION, f"Search scope {RUN}", embedder=embedder)

    assert [p.paper_title for p in passages] == ["Inside"]


async def test_search_refuses_before_embedding_anything(session, embedder):
    await workspaces.create(session, f"Search refusal {RUN}")
    with pytest.raises(InvalidInput, match="^empty_query$"):
        await library.search(session, "  ", embedder=embedder)
    with pytest.raises(NotFound, match="^unknown_workspace$") as unknown:
        await library.search(session, QUESTION, f"No such workspace {RUN}", embedder=embedder)

    # Not compared with a later read: a workspace another run commits in between (E2E on this stack) would differ.
    available = unknown.value.details["available"]
    assert f"Search refusal {RUN}" in available  # the database's collation, not Python's sort, orders the names
    assert embedder.calls == []


async def test_search_refuses_vectors_from_another_embedding_model(only_test_chunks, embedder):
    session = only_test_chunks
    query = planted_query(embedder)
    await paper_near(session, query, "Current", [0.1])
    await paper_near(session, query, "Indexed before a model change", [0.2], model="old-model")

    with pytest.raises(Conflict, match="^embedding_model_changed$"):
        await library.search(session, QUESTION, embedder=embedder)
    assert embedder.calls == []


async def test_the_card_has_details_outline_workspaces_and_every_note(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Card paper")
    for name in (f"Thesis {RUN}", f"Alpha {RUN}"):
        workspace = await workspaces.create(session, name)
        await workspaces.add_paper(session, workspace.id, paper.id)
    mine = await notes.create_human_note(
        session, "My own point.", notes.Anchor(paper.id, 2, [(72.0, 110.0, 300.0, 125.0)], "The second page describes")
    )
    ai = await notes.create_llm_note(session, paper.id, "Claims can be checked.", TWO_LINE_QUOTE)

    card = await library.paper_card(session, paper.id)

    assert (card.id, card.title, card.status, card.page_count, card.is_retracted) == (
        paper.id, "Card paper", "ready", 2, False
    )
    assert card.workspaces == [f"Alpha {RUN}", f"Thesis {RUN}"]
    assert card.sections == [library.Section("1 Introduction", 1), library.Section("2 Method", 2)]
    assert card.notes == [
        library.NoteBrief(ai.id, "llm", "Claims can be checked.", 1, TWO_LINE_QUOTE),
        library.NoteBrief(mine.id, "human", "My own point.", 2, "The second page describes"),
    ]


async def test_the_card_of_an_unknown_paper_is_not_found(session):
    with pytest.raises(NotFound):
        await library.paper_card(session, uuid.uuid4())


async def test_the_card_gives_a_note_on_the_whole_paper_no_page_or_quote(session):
    paper = Paper(title="Card paper", file_path="/nonexistent.pdf", status="ready", page_count=2)
    session.add(paper)
    await session.commit()
    note = await paper_only_note(session, paper, body="The whole paper, in one line.", provenance=Provenance.LLM)

    card = await library.paper_card(session, paper.id)

    assert card.notes == [library.NoteBrief(note.id, "llm", "The whole paper, in one line.", None, None)]
