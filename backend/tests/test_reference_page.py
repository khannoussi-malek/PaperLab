"""To read, the one in-library match, and the References page's data (M21, D121, D164–D166, D177)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select, text

from app.core import graph, references
from app.core.errors import NotFound
from app.models import ExternalRef, Note, NoteEmbedding, Paper, paper_references

# Every test here hides the owner's rows (below), as the other references tests do: one worker for all of them.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:8]  # unique DOIs, OpenAlex IDs and workspace names per run (D37)
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)  # the test transaction freezes now(): To read times are set by hand


@pytest.fixture
async def library(session):
    """The dev database (D15) holds the owner's papers, references, note vectors and notes: hide them in this test's
    rolled-back transaction, so every count is the test's own."""
    for model in (paper_references, NoteEmbedding, ExternalRef, Note, Paper):
        await session.execute(delete(model))
    return session


async def add_papers(session, *titles: str, **fields) -> list[Paper]:
    added = [Paper(**{"file_path": "/nonexistent.pdf", "title": title, **fields}) for title in titles]
    session.add_all(added)
    await session.flush()
    return added


async def add_ref(session, title: str, **fields) -> ExternalRef:
    ref = ExternalRef(title=title, **fields)
    session.add(ref)
    await session.flush()
    return ref


async def link(session, ref: ExternalRef, *linked: Paper, direction: str = "cites") -> None:
    await session.execute(
        paper_references.insert(),
        [{"paper_id": paper.id, "ref_id": ref.id, "direction": direction, "position": 0} for paper in linked],
    )


def titles(rows) -> list[str]:
    return [row.title for row in rows]


async def queued(session, ref_id) -> datetime | None:
    return await session.scalar(select(ExternalRef.queued_at).where(ExternalRef.id == ref_id))


# --- To read (D164) ----------------------------------------------------------------------------------------------


async def test_queue_marks_a_reference_once_and_unqueue_clears_it(library):
    ref = await add_ref(library, "To read later")

    assert await references.queue(library, ref.id) is not None
    await library.execute(text("UPDATE external_refs SET queued_at = :at WHERE id = :id"), {"at": T0, "id": ref.id})
    assert await references.queue(library, ref.id) == T0  # a second To read keeps the first time

    await references.unqueue(library, ref.id)
    await references.unqueue(library, ref.id)  # and a second unmark is harmless
    assert await queued(library, ref.id) is None


async def test_an_unknown_reference_can_be_neither_queued_nor_unqueued(library):
    for call in (references.queue, references.unqueue):
        with pytest.raises(NotFound):
            await call(library, uuid.uuid4())


# --- the one in-library match (D121, D165) -----------------------------------------------------------------------


async def test_the_tab_and_the_graph_compose_the_one_match():
    assert references.IN_LIBRARY in references._LISTING.text
    assert references.IN_LIBRARY in graph._EDGES


IDENTIFIERS = ["imported_as", "openalex_id", "doi_upper_cased", "arxiv_doi"]


async def matched_reference(session, identifier: str) -> tuple[Paper, Paper, ExternalRef]:
    """Two library papers cite R and R is queued, so without a match R would be co-cited and To read; a third library
    paper is R by `identifier`. Returns (a citing paper, the library paper R is, R)."""
    citing, other = await add_papers(session, "Citing one", "Citing two")
    tag = f"{RUN}{IDENTIFIERS.index(identifier)}"
    paper_fields = {
        "imported_as": {},
        "openalex_id": {"openalex_id": f"W21{tag}"},
        "doi_upper_cased": {"doi": f"10.5555/m21-{tag}"},
        "arxiv_doi": {"doi": f"10.48550/arxiv.2609.{tag}"},
    }[identifier]
    [paper] = await add_papers(session, "The reference itself", **paper_fields)
    ref_fields = {
        "imported_as": {"imported_as": paper.id},
        "openalex_id": {"openalex_id": f"W21{tag}"},
        "doi_upper_cased": {"doi": f"10.5555/M21-{tag.upper()}"},
        "arxiv_doi": {"arxiv_id": f"2609.{tag.upper()}"},
    }[identifier]
    ref = await add_ref(session, "R", queued_at=T0, **ref_fields)
    await link(session, ref, citing, other)
    return citing, paper, ref


async def tab_matches(session, citing: Paper, paper: Paper, ref: ExternalRef) -> bool:
    [row] = (await references.listing(session, citing.id, "cites")).rows
    return row.paper_id == paper.id


async def graph_matches(session, citing: Paper, paper: Paper, ref: ExternalRef) -> bool:
    links = (await graph.library_graph(session)).links
    return any((link.source, link.target, link.kind) == (citing.id, paper.id, "cites") for link in links)


CALLERS = {"tab": tab_matches, "graph": graph_matches}


@pytest.mark.parametrize("caller", list(CALLERS))
@pytest.mark.parametrize("identifier", IDENTIFIERS)
async def test_each_caller_finds_a_reference_in_the_library_by_each_identifier(library, identifier, caller):
    citing, paper, ref = await matched_reference(library, identifier)

    assert await CALLERS[caller](library, citing, paper, ref)


@pytest.mark.parametrize("lower", ["by_openalex_id", "by_doi"])
async def test_two_library_papers_matching_one_reference_show_as_the_lower_id(library, lower):
    low, high = sorted([uuid.uuid4(), uuid.uuid4()])
    by_openalex = Paper(id=low if lower == "by_openalex_id" else high, file_path="/x.pdf", title="By OpenAlex ID",
                        openalex_id=f"W21{RUN}9")  # fmt: skip
    by_doi = Paper(id=high if lower == "by_openalex_id" else low, file_path="/x.pdf", title="By DOI",
                   doi=f"10.5555/m21-{RUN}-9")  # fmt: skip
    for paper in sorted([by_openalex, by_doi], key=lambda p: p.id, reverse=True):  # the higher id is stored first,
        library.add(paper)  # so a LIMIT 1 with no ORDER BY would most likely return it
        await library.flush()
    [citing] = await add_papers(library, "Citing")
    ref = await add_ref(library, "One paper, two copies", openalex_id=f"W21{RUN}9", doi=f"10.5555/M21-{RUN.upper()}-9")
    await link(library, ref, citing)

    [row] = (await references.listing(library, citing.id, "cites")).rows

    assert row.paper_id == low
