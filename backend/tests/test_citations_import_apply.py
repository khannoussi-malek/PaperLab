"""M40 Task 7: a Zotero import becomes papers, without duplicates (D267–D269, ruling A, Review Focus 3)."""

import io
import json
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from conftest import FakeArq
from sqlalchemy import func, select

from app.core import citations_import_apply as cia
from app.core import discovery, notes, papers, queue, tags, workspaces
from app.core.candidates import Candidate
from app.core.citations_bundle_read import read_bundle
from app.core.citations_import import ImportEntry
from app.models import Note, Paper, Provenance
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
        zf.writestr("My Library.bib", bib)
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
    assert await bodies(session, paper.id) == ["A **key** idea.", "From Zotero — collection: My Library"]
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
        "title": title("closed"), "doi": doi("c"),
        "tried": [{"url": "https://pdf.example/closed", "outcome": "http_404"}], "free_copies": [],
    }]  # fmt: skip
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
    count = await session.scalar(select(func.count()).select_from(Note))
    with read_bundle(data) as bundle:
        second = await cia.apply(session, bundle.entries, workspace_id=ws.id, bundle=bundle)

    assert (first.imported, first.pdfs_attached, first.notes) == (2, 2, 3)
    assert (second.imported, second.already_in_library, second.pdfs_attached, second.notes) == (0, 2, 0, 0)
    assert len(await titled(session, "twice-a")) == 1 and len(await titled(session, "twice-b")) == 1
    assert await session.scalar(select(func.count()).select_from(Note)) == count
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
    assert len(jobs.jobs) == 2
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


async def test_a_big_import_runs_as_a_job_that_reports_progress(session, pdf_dir, jobs, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    await held(session, pdf_dir, "job0", year=2020)  # entry 0 is in the library (same title, no authors)
    data = bib_of(cia.INLINE_MAX + 1)

    job_id = await cia.start(session, "refs.bib", data, fetch_free_pdfs=False)

    [(name, path, file_name, ws, fetch)] = jobs.jobs
    assert (name, file_name, ws, fetch) == ("import_citations", "refs.bib", None, False)
    assert Path(path).read_bytes() == data and Path(path).is_relative_to(pdf_dir)
    redis = FakeRedis()
    done = await worker.import_citations({"redis": redis, "job_id": job_id}, path, file_name, ws, fetch)

    assert (done["already_in_library"], len(done["needs_pdf"])) == (1, cia.INLINE_MAX)
    keys = {key for key, _, _ in redis.writes}
    assert keys == {cia.progress_key(job_id)}
    progress = [w for _, w, _ in redis.writes]
    assert len(progress) == cia.INLINE_MAX + 2  # one per entry, then the finished result
    assert progress[0]["total"] == cia.INLINE_MAX + 1 and progress[0]["finished"] is False
    assert progress[-1]["finished"] is True and progress[-1]["already_in_library"] == 1
    assert not Path(path).exists()
