"""M40 Task 7: a Zotero import becomes papers, without duplicates (D267–D269, ruling A, Review Focus 3)."""

import asyncio
import io
import itertools
import json
import os
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from conftest import FakeArq
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app.core import citations_import_apply as cia
from app.core import discovery, notes, papers, queue, tags, workspaces
from app.core.candidates import Candidate
from app.core.citations_bundle_read import Bundle, read_bundle
from app.core.citations_import import CitationsImportError, ImportEntry
from app.models import Note, Paper, Provenance, note_papers
from app.workers import citations_import as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:10]
PDF = b"%PDF-1.7 imported"


def doi(n: str) -> str:
    return f"10.5555/m40t7.{RUN}.{n}"


def title(n: str) -> str:
    return f"Zq{RUN} {n} study of things"


def entry(n: str, **fields) -> ImportEntry:
    return ImportEntry(**{"title": title(n), "authors": ["Jane Smith", "Hans Muller"], "year": 2020, **fields})


@pytest.fixture(autouse=True)
def jobs(monkeypatch) -> FakeArq:
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing reaches a paper source unless a test serves one (fetching below)."""

    def refuse(*_):
        pytest.fail("a paper source was contacted")

    monkeypatch.setattr(discovery, "open_providers", refuse)
    monkeypatch.setattr(discovery, "search", refuse)


@pytest.fixture
def fetching(discovery_fakes, monkeypatch):
    """Paper sources answer from `found` (DOI -> Candidate); PDFs come from discovery_fakes.pdf_host."""
    found: dict[str, Candidate] = {}

    @asynccontextmanager
    async def open_providers(_session):
        yield discovery_fakes.providers

    async def search(_session, _providers, query):
        return discovery.SearchResult([found[query]] if query in found else [], [])

    monkeypatch.setattr(discovery, "open_providers", open_providers)
    monkeypatch.setattr(discovery, "search", search)
    return found, discovery_fakes.pdf_host


async def held(session, pdf_dir, n: str, **fields) -> Paper:
    return await papers.create_paper(session, "held.pdf", PDF, pdf_dir, prefill={"title": title(n), **fields})


async def titled(session, n: str) -> list[Paper]:
    return list(await session.scalars(select(Paper).where(Paper.title == title(n)).order_by(Paper.created_at)))


async def bodies(session, paper_id) -> list[str]:
    return sorted(v.body for v in await notes.list_notes(session, paper_id=paper_id))


def zipped(bib: str, members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("Reading list.bib", bib)
        for name, body in members.items():
            zf.writestr(name, body)
    return out.getvalue()


# ---- dedupe: every key attaches the held paper and never writes it ----


async def test_a_doi_in_the_library_is_attached_not_written(session, pdf_dir):
    paper = await held(session, pdf_dir, "doi", doi=doi("a"), venue="Kept venue")
    ws = await workspaces.create(session, f"Import {RUN} doi")

    result = await cia.apply(
        session, [entry("doi", doi=doi("a").upper(), venue="Other venue")], workspace_id=ws.id, fetch_free_pdfs=False
    )

    assert (result.already_in_library, result.imported) == (1, 0)
    await session.refresh(paper)
    assert paper.venue == "Kept venue" and paper.title == title("doi")
    assert [p.id for p in await titled(session, "doi")] == [paper.id]
    assert [p.id for p in await workspaces.papers(session, ws.id)] == [paper.id]


async def test_a_preprints_published_doi_is_a_match(session, pdf_dir):
    preprint = await held(
        session, pdf_dir, "pub", doi=f"10.48550/arxiv.2601.{RUN[:5]}", source_type="preprint", published_doi=doi("p")
    )
    result = await cia.apply(session, [entry("pub", doi=doi("p"))], fetch_free_pdfs=False)
    assert result.already_in_library == 1
    assert [p.id for p in await titled(session, "pub")] == [preprint.id]


async def test_an_arxiv_copy_in_the_library_is_a_match(session, pdf_dir):
    arxiv_id = f"2602.{RUN[:5]}"
    copy = await held(session, pdf_dir, "arx", doi=f"10.48550/arxiv.{arxiv_id}", source_type="preprint")
    result = await cia.apply(session, [entry("arx", doi=doi("x"), arxiv_id=arxiv_id)], fetch_free_pdfs=False)
    assert result.already_in_library == 1
    assert [p.id for p in await titled(session, "arx")] == [copy.id]


async def test_an_arxiv_entry_matches_its_published_version_by_title(session, pdf_dir):
    published = await held(
        session, pdf_dir, "ver", doi=doi("v"), authors=["Smith, Jane", "Muller, Hans"], year=2021,
        source_type="journal_article",
    )  # fmt: skip
    arxiv_entry = entry("ver", arxiv_id=f"2603.{RUN[:5]}", source_type="preprint")
    result = await cia.apply(session, [arxiv_entry], fetch_free_pdfs=False)
    assert result.already_in_library == 1
    assert [p.id for p in await titled(session, "ver")] == [published.id]


async def test_the_exact_title_and_authors_are_a_match(session, pdf_dir):
    same = await held(session, pdf_dir, "ttl", authors=["Smith, Jane"], year=2020)
    stranger = entry("ttl", authors=["Someone Else"])

    result = await cia.apply(session, [entry("ttl"), stranger], fetch_free_pdfs=False)

    assert result.already_in_library == 1 and len(result.needs_pdf) == 1
    assert [p.id for p in await titled(session, "ttl")] == [same.id]


# ---- new papers ----


async def test_a_bundled_pdf_becomes_a_locked_paper_with_ingest_queued(session, pdf_dir, jobs):
    ws = await workspaces.create(session, f"Import {RUN} bundle")
    bib = (
        f"@article{{a, title={{{title('zip')}}}, author={{Smith, Jane}}, year={{2020}}, journal={{J. Things}},"
        f" volume={{12}}, number={{3}}, pages={{45--67}}, doi={{{doi('z')}}}, issn={{1234-5678}},"
        f" keywords={{coffee, genetics}}, annote={{A <b>key</b> idea.}}, file={{files/1/a.pdf}}}}\n"
    )
    with read_bundle(zipped(bib, {"files/1/a.pdf": PDF})) as bundle:
        result = await cia.apply(session, bundle.entries, workspace_id=ws.id, bundle=bundle)

    assert (result.imported, result.pdfs_attached, result.already_in_library) == (1, 1, 0)
    [paper] = await titled(session, "zip")
    assert (paper.doi, paper.venue, paper.volume) == (doi("z"), "J. Things", "12")
    assert (paper.issue, paper.pages) == ("3", "45-67")
    assert (paper.issn, paper.source_type, paper.authors) == ("1234-5678", "journal_article", ["Jane Smith"])
    assert {"title", "doi"} <= set(paper.manual_fields)
    assert Path(paper.file_path).read_bytes() == PDF
    assert jobs.jobs == [("ingest_paper", str(paper.id))]
    assert ws.id in (await papers.get_paper(session, paper.id)).workspace_ids
    assert (await tags.paper_tag_map(session, ws.id))[paper.id] == ["coffee", "genetics"]
    assert await bodies(session, paper.id) == ["A **key** idea.", "From Zotero — collection: Reading list"]
    assert result.notes == 2


async def test_fetch_on_takes_a_free_copy(session, pdf_dir, jobs, fetching):
    found, pdf_host = fetching
    found[doi("f")] = Candidate(title=title("free"), doi=doi("f"), pdf_urls=["https://pdf.example/free"])
    pdf_host.reply("/free", 200, content=PDF)

    result = await cia.apply(session, [entry("free", doi=doi("f"), notes=["Mine."])])

    assert (result.imported, result.pdfs_attached, result.needs_pdf) == (1, 0, [])
    [paper] = await titled(session, "free")
    assert paper.doi == doi("f") and jobs.jobs == [("ingest_paper", str(paper.id))]
    assert await bodies(session, paper.id) == ["Mine."]


async def test_fetch_on_without_a_free_copy_lists_the_entry(session, pdf_dir, jobs, fetching):
    found, pdf_host = fetching
    found[doi("c")] = Candidate(title=title("closed"), doi=doi("c"), pdf_urls=["https://pdf.example/closed"])
    pdf_host.reply("/closed", 404)

    result = await cia.apply(session, [entry("closed", doi=doi("c"))])

    assert result.imported == 0 and await titled(session, "closed") == []
    assert result.needs_pdf == [{
        "title": title("closed"), "authors": ["Jane Smith", "Hans Muller"], "year": 2020, "venue": None,
        "doi": doi("c"), "arxiv_id": None, "pmid": None, "pmcid": None, "issn": None, "abstract": None,
        "volume": None, "issue": None, "pages": None, "editors": [], "source_type": "other", "tags": [],
        "collection": None, "notes": [],
        "tried": [{"url": "https://pdf.example/closed", "outcome": "http_404"}], "free_copies": [],
    }]  # fmt: skip  (the whole entry, so it can later be saved as a metadata-only paper)
    assert jobs.jobs == []


async def test_fetch_off_lists_every_pdf_less_entry_without_asking_anyone(session, pdf_dir):
    result = await cia.apply(session, [entry("off", doi=doi("o")), entry("bare")], fetch_free_pdfs=False)
    assert [(n["title"], n["doi"], n["tried"]) for n in result.needs_pdf] == [
        (title("off"), doi("o"), []),
        (title("bare"), None, []),
    ]
    assert await titled(session, "off") == []


async def test_fetch_on_skips_an_entry_with_no_doi_or_arxiv_id(session, pdf_dir, fetching):
    result = await cia.apply(session, [entry("noid")])
    assert [n["title"] for n in result.needs_pdf] == [title("noid")]


async def test_zotero_import_saves_needs_pdf_entries_without_pdf_when_asked(session, pdf_dir, jobs):
    ws = await workspaces.create(session, f"Zotero {RUN}")
    with_abstract = entry("abs", abstract="An abstract.", tags=["t1"], notes=["my note"], doi=doi("abs"))
    bare = entry("bare")

    result = await cia.apply(
        session, [with_abstract, bare], workspace_id=ws.id, fetch_free_pdfs=False, save_without_pdf=True
    )

    assert (result.saved_without_pdf, result.imported, result.needs_pdf, result.failed) == (2, 0, [], [])
    [saved] = await titled(session, "abs")
    assert (saved.has_pdf, saved.details_source, saved.abstract) == (False, "zotero", "An abstract.")
    assert saved.doi == doi("abs")
    assert saved.manual_fields == ["doi", "title"]
    assert [p.title for p in await workspaces.papers(session, ws.id)] == sorted([title("abs"), title("bare")])
    bodies = set(await session.scalars(select(Note.body).join(note_papers).where(note_papers.c.paper_id == saved.id)))
    assert "my note" in bodies and result.notes == 1
    assert jobs.jobs == [("index_abstract", str(saved.id))]  # none for the paper without an abstract


async def test_zotero_import_without_the_flag_is_unchanged(session, pdf_dir, jobs):
    result = await cia.apply(session, [entry("nosave")], fetch_free_pdfs=False)

    assert (result.saved_without_pdf, len(result.needs_pdf)) == (0, 1)
    assert await titled(session, "nosave") == [] and jobs.jobs == []


async def test_the_preview_counts_what_would_be_saved_without_a_pdf(session):
    entries = [entry("p1"), entry("p2", doi=doi("p2"))]

    on = await cia.preview(session, entries, fetch_free_pdfs=False, save_without_pdf=True)
    off = await cia.preview(session, entries, fetch_free_pdfs=False)

    assert (on.would_save_without_pdf, off.would_save_without_pdf) == (2, 0)


# ---- notes and the "From Zotero" note ----


async def test_a_library_import_keeps_tags_and_collection_in_one_note(session, pdf_dir):
    paper = await held(session, pdf_dir, "lib", doi=doi("l"))
    zotero = entry("lib", doi=doi("l"), tags=["coffee", "tea"], collection="Reading", notes=["First.", "Second."])

    result = await cia.apply(session, [zotero], fetch_free_pdfs=False)

    assert result.notes == 3
    zotero_note = "From Zotero — tags: coffee, tea; collection: Reading"
    assert await bodies(session, paper.id) == ["First.", zotero_note, "Second."]
    views = await notes.list_notes(session, paper_id=paper.id)
    assert {v.provenance for v in views} == {Provenance.HUMAN} and all(v.anchors == [] for v in views)


async def test_a_workspace_import_tags_the_paper_and_notes_only_the_collection(session, pdf_dir):
    with_collection = await held(session, pdf_dir, "wsa", doi=doi("wa"))
    without = await held(session, pdf_dir, "wsb", doi=doi("wb"))
    ws = await workspaces.create(session, f"Import {RUN} tags")
    entries = [
        entry("wsa", doi=doi("wa"), tags=["Coffee", "x" * 65], collection="Reading"),
        entry("wsb", doi=doi("wb"), tags=["coffee"]),
    ]

    await cia.apply(session, entries, workspace_id=ws.id, fetch_free_pdfs=False)

    tag_map = await tags.paper_tag_map(session, ws.id)
    assert tag_map[with_collection.id] == ["Coffee"] and tag_map[without.id] == ["Coffee"]
    # a name too long for a tag is kept in the note instead
    assert await bodies(session, with_collection.id) == [f"From Zotero — tags: {'x' * 65}; collection: Reading"]
    assert await bodies(session, without.id) == []


async def test_importing_the_same_file_twice_adds_nothing(session, pdf_dir, jobs):  # Review Focus 3
    bib = (
        f"@article{{a, title={{{title('twice-a')}}}, author={{Smith, Jane}}, year={{2020}}, doi={{{doi('ta')}}},"
        f" annote={{Note A}}, file={{files/1/a.pdf}}}}\n"
        f"@article{{b, title={{{title('twice-b')}}}, author={{Doe, Jo}}, year={{2021}}, keywords={{k}},"
        f" file={{files/2/b.pdf}}}}\n"
    )
    data = zipped(bib, {"files/1/a.pdf": PDF, "files/2/b.pdf": PDF + b"2"})
    ws = await workspaces.create(session, f"Import {RUN} twice")

    with read_bundle(data) as bundle:
        first = await cia.apply(session, bundle.entries, workspace_id=ws.id, bundle=bundle)
    ours = select(Paper.id).where(Paper.title.in_([title("twice-a"), title("twice-b")]))
    count_ours = select(func.count()).select_from(note_papers).where(note_papers.c.paper_id.in_(ours))
    count = await session.scalar(count_ours)
    with read_bundle(data) as bundle:
        second = await cia.apply(session, bundle.entries, workspace_id=ws.id, bundle=bundle)

    assert (first.imported, first.pdfs_attached, first.notes) == (2, 2, 3)
    assert (second.imported, second.already_in_library, second.pdfs_attached, second.notes) == (0, 2, 0, 0)
    assert len(await titled(session, "twice-a")) == 1 and len(await titled(session, "twice-b")) == 1
    assert count == 3 and await session.scalar(count_ours) == count
    assert len(jobs.jobs) == 2


# ---- isolation ----


async def test_one_failing_entry_leaves_no_paper_and_the_rest_go_on(session, pdf_dir, jobs, monkeypatch):
    real = cia._add_note

    async def flaky(session, paper_id, body):
        if body == "boom":
            raise RuntimeError("database hiccup")
        return await real(session, paper_id, body)

    monkeypatch.setattr(cia, "_add_note", flaky)
    bib = "".join(
        f"@article{{{n}, title={{{title(n)}}}, year={{2020}}, annote={{{body}}}, file={{files/{n}.pdf}}}}\n"
        for n, body in (("ok1", "fine"), ("bad", "boom"), ("ok2", "fine too"))
    )
    data = zipped(bib, {f"files/{n}.pdf": PDF + n.encode() for n in ("ok1", "bad", "ok2")})

    with read_bundle(data) as bundle:
        result = await cia.apply(session, bundle.entries, bundle=bundle)

    assert result.imported == 2 and result.failed == [{"title": title("bad"), "reason": cia.FAILED}]
    assert await titled(session, "bad") == []
    assert len(await titled(session, "ok1")) == 1 and len(await titled(session, "ok2")) == 1
    assert len(jobs.jobs) == 3  # ingest is queued before filing; the discarded paper's ingest finds it gone
    assert len(list(pdf_dir.glob("*.pdf"))) == 2  # the failed one's file is gone


# ---- inline or a job ----


def bib_of(count: int) -> bytes:
    return "".join(f"@article{{e{i}, title={{{title(f'job{i}')}}}, year={{2020}}}}\n" for i in range(count)).encode()


async def test_a_small_import_runs_inline(session, pdf_dir, jobs):
    result = await cia.start(session, "refs.bib", bib_of(2), fetch_free_pdfs=False)
    assert isinstance(result, cia.ImportResult) and len(result.needs_pdf) == 2
    assert jobs.jobs == []


class FakeRedis:
    def __init__(self):
        self.writes: list[tuple[str, dict, int]] = []

    async def set(self, key, value, ex=None):
        self.writes.append((key, json.loads(value), ex))


async def test_a_failed_progress_write_is_skipped_and_the_job_finishes(session, pdf_dir, jobs, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    class BlipRedis(FakeRedis):
        async def set(self, key, value, ex=None):
            if len(self.writes) == 0:
                self.writes.append(("blip", {}, 0))
                raise RedisConnectionError("blip")
            await super().set(key, value, ex)

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    data = bib_of(cia.INLINE_MAX + 1)
    job_id = await cia.start(session, "refs.bib", data, fetch_free_pdfs=False)
    [(_, path, file_name, ws, fetch, save)] = jobs.jobs
    done = await worker.import_citations({"redis": BlipRedis(), "job_id": job_id}, path, file_name, ws, fetch, save)
    assert len(done["needs_pdf"]) == cia.INLINE_MAX + 1


async def test_the_job_carries_save_without_pdf_to_the_worker(session, pdf_dir, jobs, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    data = bib_of(cia.INLINE_MAX + 1)

    job_id = await cia.start(session, "refs.bib", data, fetch_free_pdfs=False, save_without_pdf=True)

    [(_, path, file_name, ws, fetch, save)] = jobs.jobs
    assert save is True
    done = await worker.import_citations({"redis": FakeRedis(), "job_id": job_id}, path, file_name, ws, fetch, save)
    assert (done["saved_without_pdf"], done["needs_pdf"]) == (cia.INLINE_MAX + 1, [])


async def test_a_big_import_runs_as_a_job_that_reports_progress(session, pdf_dir, jobs, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    await held(session, pdf_dir, "job0", year=2020)  # entry 0 is in the library (same title, no authors)
    data = bib_of(cia.INLINE_MAX + 1)

    job_id = await cia.start(session, "refs.bib", data, fetch_free_pdfs=False)

    [(name, path, file_name, ws, fetch, save)] = jobs.jobs
    assert (name, file_name, ws, fetch) == ("import_citations", "refs.bib", None, False)
    assert Path(path).read_bytes() == data and Path(path).is_relative_to(pdf_dir)
    stale, fresh = Path(path).with_name("stale.upload"), Path(path).with_name("fresh.upload")
    stale.write_bytes(b"old")
    fresh.write_bytes(b"new")
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(stale, (two_days_ago, two_days_ago))
    redis = FakeRedis()
    done = await worker.import_citations({"redis": redis, "job_id": job_id}, path, file_name, ws, fetch, save)

    assert (done["already_in_library"], len(done["needs_pdf"])) == (1, cia.INLINE_MAX)
    keys = {key for key, _, _ in redis.writes}
    assert keys == {cia.progress_key(job_id)}
    progress = [w for _, w, _ in redis.writes]
    assert len(progress) == cia.INLINE_MAX + 3  # one before the first entry, one per entry, then the finished result
    assert progress[0]["total"] == cia.INLINE_MAX + 1 and progress[0]["finished"] is False
    assert progress[0]["done"] == 0  # the first heartbeat, before any entry
    assert progress[2]["done"] == 2 and progress[2]["needs_pdf"] == 1  # running: counts only, never the lists
    assert all(abs(p["at"] - time.time()) < 60 for p in progress)  # each write is a heartbeat
    assert all(isinstance(p["needs_pdf"], int) and isinstance(p["failed"], int) for p in progress[:-1])
    assert progress[-1]["finished"] is True and progress[-1]["already_in_library"] == 1
    assert len(progress[-1]["needs_pdf"]) == cia.INLINE_MAX and progress[-1]["not_reached"] == []
    assert {ex for _, _, ex in redis.writes} == {cia.PROGRESS_TTL}
    assert not Path(path).exists()
    assert not stale.exists() and fresh.exists()  # an upload a crashed job left behind is swept after a day


async def test_a_job_stops_before_its_timeout_and_says_what_it_did_not_reach(session, pdf_dir, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    monkeypatch.setattr(worker, "IMPORT_JOB_TIMEOUT", worker.SAFETY_MARGIN)  # no time left at all
    path = pdf_dir / "imports" / "budget.upload"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bib_of(3))
    redis = FakeRedis()

    done = await worker.import_citations({"redis": redis, "job_id": "j"}, str(path), "refs.bib", None, False)

    assert done["finished"] is True and done["needs_pdf"] == []
    assert done["not_reached"] == [title(f"job{i}") for i in range(3)]
    assert done["stopped"] == cia.STOPPED.format(done=0, total=3)
    assert "Import the same file again" in done["stopped"]


async def test_apply_stops_at_its_deadline(session, pdf_dir, monkeypatch):
    monkeypatch.setattr(cia, "_now", itertools.count().__next__)  # 0, 1, 2, ...
    entries = [entry(f"dl{i}") for i in range(4)]

    result = await cia.apply(session, entries, fetch_free_pdfs=False, deadline=2)

    assert len(result.needs_pdf) == 2 and result.not_reached == [title("dl2"), title("dl3")]
    assert result.stopped == cia.STOPPED.format(done=2, total=4)


# ---- inline only without network ----


async def test_an_import_that_would_fetch_goes_to_the_job_even_when_small(session, pdf_dir, jobs):
    data = f"@article{{a, title={{{title('jf')}}}, year={{2020}}, doi={{{doi('jf')}}}}}\n".encode()

    job_id = await cia.start(session, "refs.bib", data)  # fetch on by default; nothing is contacted here

    assert isinstance(job_id, str) and [j[0] for j in jobs.jobs] == ["import_citations"]
    assert await titled(session, "jf") == []


async def test_a_dedupe_only_import_stays_inline_with_fetch_on(session, pdf_dir, jobs):
    paper = await held(session, pdf_dir, "inl", doi=doi("inl"))
    data = f"@article{{a, title={{{title('inl')}}}, year={{2020}}, doi={{{doi('inl')}}}}}\n".encode()

    result = await cia.start(session, "refs.bib", data)

    assert isinstance(result, cia.ImportResult) and result.already_in_library == 1 and jobs.jobs == []
    assert [p.id for p in await titled(session, "inl")] == [paper.id]


# ---- ingest first, then filing ----


async def test_ingest_is_queued_before_the_paper_is_filed(session, pdf_dir, jobs, monkeypatch):
    real = cia._file
    seen = []

    async def filing(session, paper_id, entry, workspace_id):
        seen.append(list(jobs.jobs))
        return await real(session, paper_id, entry, workspace_id)

    monkeypatch.setattr(cia, "_file", filing)
    bib = f"@article{{a, title={{{title('order')}}}, year={{2020}}, file={{files/1/a.pdf}}}}\n"
    with read_bundle(zipped(bib, {"files/1/a.pdf": PDF})) as bundle:
        await cia.apply(session, bundle.entries, bundle=bundle)

    [paper] = await titled(session, "order")
    assert seen == [[("ingest_paper", str(paper.id))]]


# ---- a damaged PDF in the zip ----


def damaged(monkeypatch):
    def read_pdf(self, member):
        raise CitationsImportError("This zip is damaged, so nothing was imported.")

    monkeypatch.setattr(Bundle, "read_pdf", read_pdf)


async def test_a_damaged_bundled_pdf_falls_back_to_a_free_copy(session, pdf_dir, jobs, fetching, monkeypatch):
    found, pdf_host = fetching
    found[doi("dmg")] = Candidate(title=title("dmg"), doi=doi("dmg"), pdf_urls=["https://pdf.example/dmg"])
    pdf_host.reply("/dmg", 200, content=PDF)
    damaged(monkeypatch)
    bib = f"@article{{a, title={{{title('dmg')}}}, year={{2020}}, doi={{{doi('dmg')}}}, file={{files/1/a.pdf}}}}\n"

    with read_bundle(zipped(bib, {"files/1/a.pdf": PDF})) as bundle:
        result = await cia.apply(session, bundle.entries, bundle=bundle)

    assert (result.imported, result.pdfs_attached, result.failed) == (1, 0, [])
    assert len(await titled(session, "dmg")) == 1


async def test_a_damaged_bundled_pdf_fails_with_fetch_off(session, pdf_dir, monkeypatch):
    damaged(monkeypatch)
    bib = f"@article{{a, title={{{title('dmg2')}}}, year={{2020}}, doi={{{doi('dmg2')}}}, file={{files/1/a.pdf}}}}\n"

    with read_bundle(zipped(bib, {"files/1/a.pdf": PDF})) as bundle:
        result = await cia.apply(session, bundle.entries, bundle=bundle, fetch_free_pdfs=False)

    assert result.failed == [{"title": title("dmg2"), "reason": "This zip is damaged, so nothing was imported."}]


# ---- final review wave ----


async def test_a_slow_entry_is_cut_at_the_deadline_and_the_rest_listed(session, pdf_dir, fetching, monkeypatch):
    async def slow(*_):
        await asyncio.sleep(30)

    monkeypatch.setattr(cia, "_fetch", slow)
    entries = [entry("fast"), entry("slow", doi=doi("slow")), entry("after", doi=doi("after"))]

    started = time.monotonic()
    result = await cia.apply(session, entries, deadline=time.monotonic() + 0.3)

    assert time.monotonic() - started < 5
    assert [n["title"] for n in result.needs_pdf] == [title("fast")]
    assert result.not_reached == [title("slow"), title("after")]
    assert result.stopped == cia.STOPPED.format(done=1, total=3)


async def test_a_long_note_is_cut_to_the_notes_limit_once(session, pdf_dir):
    paper = await held(session, pdf_dir, "long", doi=doi("long"))
    long_entry = entry("long", doi=doi("long"), notes=["w" * 60_000])

    await cia.apply(session, [long_entry], fetch_free_pdfs=False)
    again = await cia.apply(session, [long_entry], fetch_free_pdfs=False)

    [body] = await bodies(session, paper.id)
    assert len(body) == cia.NOTE_MAX_CHARS and body.endswith(cia.NOTE_CUT)
    assert again.notes == 0


async def test_a_fetched_paper_keeps_what_the_entry_knows_and_what_the_fetch_found(session, pdf_dir, fetching):
    found, pdf_host = fetching
    found[doi("meta")] = Candidate(
        title=title("meta"), doi=doi("meta"), abstract="Found abstract", pdf_urls=["https://pdf.example/meta"]
    )
    pdf_host.reply("/meta", 200, content=PDF)
    zotero = entry(
        "meta", doi=doi("meta"), abstract="Zotero abstract", volume="7", issue="2", pages="1-9",
        editors=["Ed Itor"], pmid="42", pmcid="PMC42", source_type="journal_article",
    )  # fmt: skip

    await cia.apply(session, [zotero])

    [paper] = await titled(session, "meta")
    assert paper.abstract == "Found abstract"  # the fetch's own value wins
    assert (paper.volume, paper.issue, paper.pages, paper.editors) == ("7", "2", "1-9", ["Ed Itor"])
    assert (paper.pmid, paper.pmcid) == ("42", "PMC42")
    assert (paper.source_type, paper.peer_reviewed) == ("journal_article", "true")


async def test_fetch_tries_the_arxiv_id_when_the_doi_has_no_free_copy(session, pdf_dir, fetching):
    found, pdf_host = fetching
    arxiv_id = f"2604.{RUN[:5]}"
    found[doi("both")] = Candidate(title=title("both"), doi=doi("both"), pdf_urls=["https://pdf.example/shut"])
    found[arxiv_id] = Candidate(
        title=title("both"), external_ids={"arxiv": arxiv_id}, pdf_urls=["https://pdf.example/arx"]
    )
    pdf_host.reply("/shut", 404)
    pdf_host.reply("/arx", 200, content=PDF)

    result = await cia.apply(session, [entry("both", doi=doi("both"), arxiv_id=arxiv_id)])

    assert result.imported == 1 and len(await titled(session, "both")) == 1


async def test_fetch_lists_both_attempts_when_neither_has_a_copy(session, pdf_dir, fetching):
    found, pdf_host = fetching
    arxiv_id = f"2605.{RUN[:5]}"
    found[doi("none")] = Candidate(title=title("none"), doi=doi("none"), pdf_urls=["https://pdf.example/shut"])
    pdf_host.reply("/shut", 404)

    result = await cia.apply(session, [entry("none", doi=doi("none"), arxiv_id=arxiv_id)])

    assert result.needs_pdf[0]["tried"] == [
        {"url": "https://pdf.example/shut", "outcome": "http_404"},
        {"url": f"https://arxiv.org/abs/{arxiv_id}", "outcome": "no_match"},
    ]


async def test_preview_counts_without_contacting_anyone(session, pdf_dir):
    await held(session, pdf_dir, "pv-held", doi=doi("pvh"))
    bib = (
        f"@article{{a, title={{{title('pv-held')}}}, doi={{{doi('pvh')}}}}}\n"
        f"@article{{b, title={{{title('pv-zip')}}}, year={{2020}}, file={{files/1/b.pdf}}}}\n"
        f"@article{{c, title={{{title('pv-fetch')}}}, doi={{{doi('pvf')}}}}}\n"
        f"@article{{d, title={{{title('pv-bare')}}}}}\n"
    )
    with read_bundle(zipped(bib, {"files/1/b.pdf": PDF})) as bundle:
        on = await cia.preview(session, bundle.entries, bundle=bundle)
        off = await cia.preview(session, bundle.entries, bundle=bundle, fetch_free_pdfs=False)

    assert on == cia.ImportPreview(
        total=4, already_in_library=1, with_bundled_pdf=1, would_fetch=1, cannot_import_without_fetch=2
    )
    assert off.would_fetch == 0 and off.cannot_import_without_fetch == 2
    assert await titled(session, "pv-zip") == []
