"""A busy source is not the same as no free copy: such a paper gets its PDF without anyone adding it again."""

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from conftest import FakeArq
from sqlalchemy import delete

from app.core import discovery, papers, pdf_recheck, pipeline, queue
from app.models import Paper, PaperSources
from app.models.workspace import Workspace
from app.workers import pdf_recheck as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]
PDF = b"%PDF-1.7 a paper"


@pytest.mark.parametrize(
    ("outcome", "temporary"),
    [
        ("busy", True), ("http_429", True), ("http_500", True), ("http_503", True), ("http_408", True),
        ("error: ConnectError", True), ("error: ReadTimeout", True),
        ("no_match", False), ("no_copy", False), ("not_a_pdf", False), ("bot_check", False), ("http_403", False),
        ("http_404", False), ("too_large", False), ("unsafe_url", False), ("pdf", False), ("links_found", False),
    ],
)
def test_which_outcomes_may_succeed_later(outcome, temporary):
    assert discovery.is_temporary(outcome) is temporary


def test_temporary_failures_picks_only_those():
    tried = [{"url": "a", "outcome": "no_match"}, {"url": "b", "outcome": "http_429"}]
    assert discovery.temporary_failures(tried) == [{"url": "b", "outcome": "http_429"}]


@pytest.fixture
def arq(monkeypatch):
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


async def saved_paper(session, **fields) -> Paper:
    prefill = {"title": f"Paper {uuid.uuid4().hex[:8]}", "doi": f"10.5555/{uuid.uuid4().hex[:8]}", **fields}
    return await papers.create_metadata_paper(session, prefill, "crossref", looked_for_pdf=True)


async def test_a_paper_that_failed_only_for_temporary_reasons_gets_its_pdf_on_the_retry(session, arq, monkeypatch):
    await session.execute(delete(PaperSources))
    paper = await saved_paper(session)
    answers = iter([(None, [{"url": "https://x.org/a.pdf", "outcome": "http_429"}], []),
                    (PDF, [{"url": "https://x.org/a.pdf", "outcome": "pdf"}], [])])

    async def find_pdf(*_args):
        return next(answers)

    attached = []

    async def attach_pdf(_session, paper_id, data, how):
        attached.append((paper_id, data, how))

    monkeypatch.setattr(discovery, "find_pdf", find_pdf)
    monkeypatch.setattr(papers, "attach_pdf", attach_pdf)

    assert await pdf_recheck.recheck(session, object(), paper.id) == "temporary"
    await session.refresh(paper)
    assert paper.pdf_check_result == "temporary"
    assert attached == []

    assert await pdf_recheck.recheck(session, object(), paper.id) == "found"
    assert attached == [(paper.id, PDF, "imported")]
    assert ("ingest_paper", str(paper.id)) in arq.jobs


async def test_no_copy_is_not_retried_soon(session, arq, monkeypatch):
    paper = await saved_paper(session)

    async def find_pdf(*_args):
        return None, [{"url": "arxiv.org (title search)", "outcome": "no_match"}], []

    monkeypatch.setattr(discovery, "find_pdf", find_pdf)
    assert await pdf_recheck.recheck(session, object(), paper.id) == "none"
    assert arq.jobs == []


async def test_a_retry_is_deferred_and_backs_off_then_stops(session, arq):
    await session.execute(delete(PaperSources))
    paper_id = uuid.uuid4()
    for attempt, delay in enumerate(pdf_recheck.RETRY_DELAYS):
        assert await pdf_recheck.schedule_retry(session, paper_id, attempt) is True
        assert arq.deferred[-1] == delay
    assert len(arq.jobs) == len(pdf_recheck.RETRY_DELAYS)
    assert await pdf_recheck.schedule_retry(session, paper_id, len(pdf_recheck.RETRY_DELAYS)) is False  # weekly now


async def test_turning_the_recheck_off_in_settings_stops_automatic_retries(session, arq):
    await session.execute(delete(PaperSources))
    session.add(PaperSources(id=True, pdf_recheck_enabled=False))
    await session.flush()
    assert await pdf_recheck.schedule_retry(session, uuid.uuid4()) is False
    assert arq.jobs == []


@pytest.fixture
def job_session(session, monkeypatch):
    @asynccontextmanager
    async def shared():
        yield session

    @asynccontextmanager
    async def no_providers(_session):
        yield object()

    monkeypatch.setattr(worker, "SessionLocal", shared)
    monkeypatch.setattr(discovery, "open_providers", no_providers)


async def test_the_retry_job_chains_while_sources_stay_busy_and_ends_on_an_answer(
    session, arq, job_session, monkeypatch
):
    await session.execute(delete(PaperSources))
    paper = await saved_paper(session)
    outcomes = iter(["temporary", "none"])

    async def recheck(_session, _providers, _paper_id):
        return next(outcomes)

    monkeypatch.setattr(pdf_recheck, "recheck", recheck)
    await worker.retry_free_pdf({}, str(paper.id), 0)
    assert arq.jobs == [("retry_free_pdf", str(paper.id), 1)]
    await worker.retry_free_pdf({}, str(paper.id), 1)
    assert len(arq.jobs) == 1


async def test_saved_without_pdf_after_a_busy_source_says_so_and_schedules_a_retry(session, arq, monkeypatch):
    await session.execute(delete(PaperSources))
    paper = await saved_paper(session)
    tried = [{"url": "https://arxiv.org/pdf/2605.13776", "outcome": "http_429"}]
    result = pipeline.AddPaperResult(status="saved_without_pdf", paper_id=paper.id, title=paper.title, tried=tried)
    finished = await pipeline._note_temporary_failures(session, result)
    assert finished.temporary_failures == tried and finished.retry_scheduled is True
    assert "tried again" in finished.note
    assert arq.jobs == [("retry_free_pdf", str(paper.id), 0)]


async def test_saved_without_pdf_with_no_copy_anywhere_schedules_nothing(session, arq):
    tried = [{"url": "arxiv.org (title search)", "outcome": "no_match"}]
    result = pipeline.AddPaperResult(status="saved_without_pdf", paper_id=uuid.uuid4(), tried=tried)
    finished = await pipeline._note_temporary_failures(session, result)
    assert finished.temporary_failures == [] and finished.retry_scheduled is False and arq.jobs == []


async def test_no_free_pdf_after_a_busy_source_tells_the_caller_what_to_do(session, arq):
    tried = [{"url": "https://x.org/a.pdf", "outcome": "error: ConnectError"}]
    result = pipeline.AddPaperResult(status="no_free_pdf", tried=tried)
    finished = await pipeline._note_temporary_failures(session, result)
    assert finished.retry_scheduled is False and "save_without_pdf" in finished.note and arq.jobs == []


async def test_a_paper_already_held_is_retried_too_when_its_new_look_met_a_busy_source(session, arq):
    await session.execute(delete(PaperSources))
    tried = [{"url": "https://x.org/a.pdf", "outcome": "busy"}]
    result = pipeline.AddPaperResult(
        status="already_in_library", paper_id=uuid.uuid4(), tried=tried, note=pipeline.NO_COPY_NOTE,
    )
    finished = await pipeline._note_temporary_failures(session, result)
    assert finished.retry_scheduled is True and finished.note != pipeline.NO_COPY_NOTE


async def workspace_with(session, papers_):
    from app.core import workspaces

    workspace = Workspace(name=f"Recheck {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    for paper in papers_:
        await workspaces.add_paper(session, workspace.id, paper.id)
    return workspace


async def test_the_batch_tool_queues_a_workspaces_papers_without_a_pdf_once(session, arq, monkeypatch):
    missing = await saved_paper(session)
    has_pdf = await saved_paper(session)
    has_pdf.file_path = "held.pdf"
    await session.flush()
    workspace = await workspace_with(session, [missing, has_pdf])

    first = await pipeline.recheck_free_copies(session, workspace.name)
    assert (first.queued, first.already_running) == (1, False)
    assert arq.jobs == [("recheck_papers", [str(missing.id)])]

    again = await pipeline.recheck_free_copies(session, workspace.name)
    assert again.already_running is True and len(arq.jobs) == 1


async def test_the_batch_tool_scopes_to_a_tag(session, arq):
    from app.core import tags

    tagged, other = await saved_paper(session), await saved_paper(session)
    workspace = await workspace_with(session, [tagged, other])
    await tags.tag_papers(session, workspace.id, "read me", [tagged.id], ())
    out = await pipeline.recheck_free_copies(session, workspace.name, tags_=["read me"])
    assert out.queued == 1 and arq.jobs == [("recheck_papers", [str(tagged.id)])]


async def test_the_batch_job_rechecks_each_paper_and_schedules_retries_for_busy_ones(
    session, arq, job_session, monkeypatch
):
    await session.execute(delete(PaperSources))
    busy, fine = await saved_paper(session), await saved_paper(session)
    outcomes = {busy.id: "temporary", fine.id: "found"}

    async def recheck(_session, _providers, paper_id):
        return outcomes[paper_id]

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(pdf_recheck, "recheck", recheck)
    monkeypatch.setattr(pdf_recheck, "sleep", no_sleep)
    counts = await worker.recheck_papers({}, [str(busy.id), str(fine.id)])
    assert counts["temporary"] == 1 and counts["found"] == 1
    assert arq.jobs == [("retry_free_pdf", str(busy.id), 0)]


def _unpaywall(handler):
    from app.providers import unpaywall

    return unpaywall.new_client(email="me@example.org", transport=httpx.MockTransport(handler))


class Providers:
    def __init__(self, http):
        self.http = http

    def client(self, source):
        return self.http if source == "unpaywall" else None


async def test_tried_lists_the_unpaywall_lookup_whatever_it_said():
    from app.core.candidates import Candidate

    paper = Candidate(title="t", doi="10.1/x")

    async def lookup(handler):
        async with _unpaywall(handler) as http:
            found, entry = await discovery._unpaywall_lookup(Providers(http), paper)
        return found.pdf_urls, entry

    urls, entry = await lookup(lambda r: httpx.Response(200, json={"oa_locations": []}))
    assert urls == [] and entry == [{"url": discovery.UNPAYWALL_LOOKUP, "outcome": "no_copy"}]

    urls, entry = await lookup(lambda r: httpx.Response(404))
    assert entry[0]["outcome"] == "no_copy"

    located = {"best_oa_location": {"url_for_pdf": "https://x.org/a.pdf"}, "oa_locations": []}
    urls, entry = await lookup(lambda r: httpx.Response(200, json=located))
    assert urls == ["https://x.org/a.pdf"] and entry[0]["outcome"] == "links_found"

    urls, entry = await lookup(lambda r: httpx.Response(429))
    assert entry[0]["outcome"] == "busy" and discovery.is_temporary(entry[0]["outcome"])

    def down(request):
        raise httpx.ConnectError("no route")

    urls, entry = await lookup(down)
    assert entry[0]["outcome"] == "error: ConnectError"


async def test_tried_says_why_unpaywall_was_skipped():
    from app.core.candidates import Candidate

    _, entry = await discovery._unpaywall_lookup(Providers(None), Candidate(title="t", doi="10.1/x"))
    assert entry == [{"url": discovery.UNPAYWALL_LOOKUP, "outcome": "skipped: off or no contact email"}]
    _, entry = await discovery._unpaywall_lookup(Providers(None), Candidate(title="t"))
    assert entry == []  # no DOI: nothing to look up



async def test_a_paper_that_has_its_pdf_is_left_out_of_the_retry_and_the_note(session, arq):
    paper = await saved_paper(session)
    paper.file_path = "held.pdf"
    await session.flush()
    tried = [{"url": "https://x.org/a.pdf", "outcome": "http_429"}]
    result = pipeline.AddPaperResult(status="already_in_library", paper_id=paper.id, tried=tried)
    assert await pipeline._note_temporary_failures(session, result) == result
    assert arq.jobs == []


async def test_a_retry_already_queued_still_counts_as_scheduled(session, arq):
    await session.execute(delete(PaperSources))
    paper_id = uuid.uuid4()
    assert await pdf_recheck.schedule_retry(session, paper_id) is True
    assert await pdf_recheck.schedule_retry(session, paper_id) is True
    assert len(arq.jobs) == 1


async def test_a_queue_outage_does_not_fail_an_add_that_already_saved_the_paper(session, monkeypatch):
    await session.execute(delete(PaperSources))
    paper = await saved_paper(session)

    async def down(*_args, **_kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(queue, "enqueue", down)
    tried = [{"url": "https://x.org/a.pdf", "outcome": "busy"}]
    result = pipeline.AddPaperResult(status="saved_without_pdf", paper_id=paper.id, tried=tried)
    finished = await pipeline._note_temporary_failures(session, result)
    assert finished.retry_scheduled is False and finished.note == pipeline.NO_RETRY_NOTE


async def test_a_retry_look_updates_when_the_paper_was_last_checked(session, arq, monkeypatch):
    from datetime import datetime, timezone

    paper = await saved_paper(session)
    before = datetime(2020, 1, 1, tzinfo=timezone.utc)
    paper.pdf_checked_at = before
    await session.flush()

    async def find_pdf(*_args):
        return None, [{"url": "a", "outcome": "busy"}], []

    monkeypatch.setattr(discovery, "find_pdf", find_pdf)
    await pdf_recheck.recheck(session, object(), paper.id)
    await session.refresh(paper)
    assert paper.pdf_checked_at > before
