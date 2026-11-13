"""A note is embedded when it is saved (M8.6 C7), not at the next references fetch."""

import uuid
from contextlib import asynccontextmanager

import pytest
from conftest import FakeArq, FakeEmbedder
from sqlalchemy import select

from app.core import notes, queue, references
from app.models import NoteEmbedding, Paper
from app.workers import references as references_worker

pytestmark = pytest.mark.anyio


@pytest.fixture
def jobs(monkeypatch) -> FakeArq:
    """Every enqueue goes to a fake pool: no test reaches Redis."""
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


@pytest.fixture
def worker_session(session, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(references_worker, "SessionLocal", shared_session)
    return session


async def make_paper(session) -> Paper:
    paper = Paper(title="test paper", file_path="/nonexistent.pdf")
    session.add(paper)
    await session.commit()
    return paper


async def embedded(session, *note_ids: uuid.UUID) -> set[uuid.UUID]:
    """Which of these notes have a vector."""
    return set(await session.scalars(select(NoteEmbedding.note_id).where(NoteEmbedding.note_id.in_(note_ids))))


def enqueued(jobs: FakeArq) -> list[tuple]:
    return [job for job in jobs.jobs if job[0] == "embed_note"]


async def test_creating_a_note_enqueues_one_embed_note(session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "a new thought")

    assert enqueued(jobs) == [("embed_note", [str(note.id)])]


async def test_editing_the_body_enqueues_the_note(session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "first")
    jobs.jobs.clear()

    await notes.update_note(session, note.id, body="second")

    assert enqueued(jobs) == [("embed_note", [str(note.id)])]


async def test_recolouring_does_not_enqueue(session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "same words")
    jobs.jobs.clear()

    await notes.update_note(session, note.id, color="#ffd54f")

    assert enqueued(jobs) == []


async def test_a_failed_enqueue_does_not_fail_the_save(session, monkeypatch):
    class DownPool:
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(queue, "_pool", DownPool())
    paper = await make_paper(session)

    note = await notes.create_paper_note(session, paper.id, "saved anyway")

    assert note.body == "saved anyway"


async def test_the_job_embeds_exactly_that_note(session, worker_session, jobs):
    paper = await make_paper(session)
    wanted = await notes.create_paper_note(session, paper.id, "the one")
    other = await notes.create_paper_note(session, paper.id, "not this one")
    embedder = FakeEmbedder(name="test-model")

    await references_worker.embed_note({"embedder": embedder}, str(wanted.id))

    assert await embedded(session, wanted.id, other.id) == {wanted.id}
    row = await session.get(NoteEmbedding, wanted.id)
    assert row.embed_model == "test-model"
    assert embedder.calls == [(["search_document: the one"], {})]


async def test_the_job_with_no_search_model_is_a_no_op(session, worker_session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "nothing to embed with")

    await references_worker.embed_note({"embedder": None}, str(note.id))

    assert await embedded(session, note.id) == set()


async def test_the_job_is_quiet_when_the_source_refuses(session, worker_session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "refused")
    refusing = FakeEmbedder(refuse="Can't reach ollama.test")

    await references_worker.embed_note({"embedder": refusing}, str(note.id))

    assert await embedded(session, note.id) == set()


async def test_embed_notes_counts_what_it_embedded(session):
    paper = await make_paper(session)
    first = await notes.create_paper_note(session, paper.id, "one")
    second = await notes.create_paper_note(session, paper.id, "two")
    embedder = FakeEmbedder()

    assert await references.embed_notes(session, embedder, [first.id]) == 1
    assert await references.embed_notes(session, embedder, [first.id]) == 0  # current now, so nothing stale
    assert await references.embed_notes(session, embedder, [second.id]) == 1
    assert await references.embed_notes(session, None, [second.id]) == 0


async def test_embed_new_still_embeds_stale_notes(session, jobs):
    paper = await make_paper(session)
    note = await notes.create_paper_note(session, paper.id, "saved before the job existed")
    jobs.jobs.clear()

    await references.embed_new(session, FakeEmbedder())

    assert await embedded(session, note.id) == {note.id}


async def test_an_import_of_many_notes_queues_one_job(session, jobs):
    from app.core import notes

    ids = [uuid.uuid4() for _ in range(3)]
    await notes.queue_embed(*ids)
    assert enqueued(jobs) == [("embed_note", [str(i) for i in ids])]


async def test_queueing_nothing_queues_no_job(session, jobs):
    from app.core import notes

    await notes.queue_embed()
    assert enqueued(jobs) == []
