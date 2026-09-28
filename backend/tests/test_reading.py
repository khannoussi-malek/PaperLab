"""The reader's own record of a paper: passes finished and their decision (M21, D118, D119, D163)."""

import uuid

import pytest
from conftest import recorded
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_enrichment import BERT_DOI, BERT_WORK, hints

from app.core import enrichment, graph, papers, workspaces
from app.core.errors import InvalidInput, NotFound
from app.models import ExternalRef, Paper
from app.workers import ingest

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)


async def add_paper(session, **fields) -> Paper:
    paper = Paper(**{"file_path": "/nonexistent.pdf", "title": f"Reading {RUN}", **fields})
    session.add(paper)
    await session.commit()
    return paper


# --- the columns (D119, D120) ------------------------------------------------------------------------------------


async def test_a_new_paper_starts_unread_and_undecided_and_a_reference_unqueued(session):
    paper, ref = await add_paper(session), ExternalRef(title=f"A reference {RUN}")
    session.add(ref)
    await session.commit()
    await session.refresh(paper)
    await session.refresh(ref)

    assert (paper.reading_pass, paper.triage, ref.queued_at) == (0, None, None)


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("reading_pass", 4, "papers_reading_pass_range"),
        ("reading_pass", -1, "papers_reading_pass_range"),
        ("triage", "maybe", "papers_triage_value"),
    ],
)
async def test_the_database_refuses_a_level_or_a_decision_it_does_not_know(session, column, value, constraint):
    paper = await add_paper(session)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(
            text(f"UPDATE papers SET {column} = :value WHERE id = :id"), {"value": value, "id": paper.id}
        )
    await session.rollback()


# --- set_reading (D163) ------------------------------------------------------------------------------------------

METADATA = ("title", "authors", "year", "venue", "doi", "abstract", "is_retracted", "status", "manual_fields")


def metadata(paper: Paper) -> dict:
    return {column: getattr(paper, column) for column in METADATA}


@pytest.mark.parametrize("level", [0, 1, 2, 3])
async def test_each_level_is_stored_and_nothing_else_changes(session, level):
    paper = await add_paper(session, triage="keep", year=2021, manual_fields=["year"])
    before = metadata(paper)

    saved = await papers.set_reading(session, paper.id, {"reading_pass": level})

    assert (saved.reading_pass, saved.triage) == (level, "keep")
    assert metadata(saved) == before  # manual_fields included: the reading state is never a correction


@pytest.mark.parametrize("triage", ["keep", "later", "drop", None])
async def test_each_decision_is_stored_and_the_level_is_kept(session, triage):
    paper = await add_paper(session, reading_pass=2, triage="later", manual_fields=["title"])
    before = metadata(paper)

    saved = await papers.set_reading(session, paper.id, {"triage": triage})

    assert (saved.reading_pass, saved.triage) == (2, triage)
    assert metadata(saved) == before


async def test_a_decision_is_not_a_workspace_and_draws_no_link(session):
    """D119: two papers set to Later share no workspace, no graph link and no chat scope."""
    paper, other = await add_paper(session), await add_paper(session, title=f"Other {RUN}")
    workspace = await workspaces.create(session, f"Reading {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)

    async def state():
        links = {
            (link.source, link.target, link.kind)
            for link in (await graph.library_graph(session)).links
            if {paper.id, other.id} & {link.source, link.target}
        }
        scope = [member.id for member in await workspaces.papers(session, workspace.id)]
        every = [(view.id, view.paper_count) for view in await workspaces.list_workspaces(session)]
        return links, scope, every

    before = await state()
    for later in (paper, other):
        await papers.set_reading(session, later.id, {"triage": "later"})

    assert await state() == before


@pytest.mark.parametrize(
    ("changes", "code", "details"),
    [
        ({"reading_pass": 4}, "reading_pass_out_of_range", {"allowed": [0, 3]}),
        ({"reading_pass": -1}, "reading_pass_out_of_range", {"allowed": [0, 3]}),
        ({"triage": "maybe"}, "unknown_triage", {"allowed": ["keep", "later", "drop"]}),
        ({}, "nothing_to_set", {}),
    ],
)
async def test_a_level_or_decision_it_does_not_know_is_refused(session, changes, code, details):
    paper = await add_paper(session)

    with pytest.raises(InvalidInput, match=f"^{code}$") as refused:
        await papers.set_reading(session, paper.id, changes)

    assert refused.value.details == details


async def test_an_unknown_paper_is_not_found(session):
    with pytest.raises(NotFound):
        await papers.set_reading(session, uuid.uuid4(), {"triage": "keep"})


async def test_a_reingest_keeps_the_level_and_the_decision(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, file_path=str(sample_pdf), title="placeholder")
    await ingest.ingest_paper(ctx, str(paper.id))
    await papers.set_reading(worker_session, paper.id, {"reading_pass": 2, "triage": "later"})

    await ingest.ingest_paper(ctx, str(paper.id))

    await worker_session.refresh(paper)
    assert (paper.status, paper.reading_pass, paper.triage, paper.manual_fields) == ("ready", 2, "later", [])


async def test_enrichment_and_a_correction_keep_the_level_and_the_decision(session, fake_openalex):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session, title="BERT: Pre-training of Deep Bidirectional Transformers for")
    await papers.set_reading(session, paper.id, {"reading_pass": 1, "triage": "keep"})

    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints(doi=BERT_DOI))
    await enrichment.correct_metadata(session, paper.id, {"title": "BERT, corrected"})

    await session.refresh(paper)
    assert (paper.openalex_id, paper.title, paper.reading_pass, paper.triage) == (
        "W2963341956", "BERT, corrected", 1, "keep"
    )  # fmt: skip
    assert paper.manual_fields == ["title"]


# --- PUT /api/papers/{id}/reading --------------------------------------------------------------------------------


async def test_put_reading_saves_either_field_and_answers_the_paper(client, session):
    paper = await add_paper(session)
    url = f"/api/papers/{paper.id}/reading"

    level = await client.put(url, json={"reading_pass": 2})
    decision = await client.put(url, json={"triage": "later"})

    assert (level.status_code, level.json()["reading_pass"], level.json()["triage"]) == (200, 2, None)
    assert (decision.status_code, decision.json()["reading_pass"], decision.json()["triage"]) == (200, 2, "later")
    listed = next(p for p in (await client.get("/api/papers")).json() if p["id"] == str(paper.id))
    assert (listed["reading_pass"], listed["triage"]) == (2, "later")
    assert (await client.put(url, json={"triage": None})).json()["triage"] is None


async def test_put_reading_refuses_an_unknown_paper_and_every_bad_body(client, session):
    paper = await add_paper(session)
    url = f"/api/papers/{paper.id}/reading"

    assert (await client.put(f"/api/papers/{uuid.uuid4()}/reading", json={"triage": "keep"})).status_code == 404
    for body in [
        {},
        {"reading_pass": 4},
        {"reading_pass": -1},
        {"reading_pass": None},
        {"triage": "maybe"},
        {"triage": "keep", "extra": 1},
    ]:
        assert (await client.put(url, json=body)).status_code == 422, body
