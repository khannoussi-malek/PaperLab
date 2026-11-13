"""M35a Task 2: a package imports as a new workspace (Review Focus 1, 2, 3, 5), all or nothing."""

import io
import json
import stat
import uuid
import zipfile

import pytest
from conftest import FakeArq
from sqlalchemy import func, select

from app.core import papers, pipeline, queue, tags, workspace_package, workspaces
from app.core.errors import InvalidInput
from app.models import Paper, PaperStatus, Workspace, note_papers
from app.models.workspace import workspace_papers
from tests.test_workspace_package_export import PDF as SEEDED_PDF
from tests.test_workspace_package_export import _seeded

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7 package import test PDF body"
RUN = uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def jobs(monkeypatch) -> FakeArq:
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


def _zip(members: dict[str, bytes], *, extra: list[zipfile.ZipInfo] | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
        for info in extra or []:
            zf.writestr(info, b"")
    return out.getvalue()


def _package(
    *,
    papers=(),
    notes=(),
    tags_=(),
    pdfs: dict[str, bytes] | None = None,
    name="Imported review",
    format_name="paperlab-workspace",
    version=1,
    description=None,
) -> bytes:
    manifest = {
        "format": format_name,
        "format_version": version,
        "paperlab_version": "0.1.0",
        "created_at": "2026-11-01T10:00:00+00:00",
        "workspace": {
            "name": name,
            "description": description,
            "research_question": "Does X?",
            "inclusion_criteria": "RCTs",
            "exclusion_criteria": None,
        },
        "counts": {"papers": len(papers), "notes": len(notes), "pdfs": len(pdfs or {})},
    }
    members = {
        "manifest.json": json.dumps(manifest),
        "papers.json": json.dumps({"papers": list(papers)}),
        "notes.json": json.dumps({"notes": list(notes)}),
        "tags.json": json.dumps({"tags": list(tags_)}),
        "screening.json": json.dumps({"runs": [], "hits": []}),
        "prisma.json": json.dumps({"identified": 0}),
    }
    members |= {f"pdfs/{key}.pdf": data.decode("latin-1") for key, data in (pdfs or {}).items()}
    return _zip({k: v.encode() if isinstance(v, str) else v for k, v in members.items()})


def _paper(key: str, title: str, **fields) -> dict:
    base = {"key": key, "title": f"{title} {RUN}", "authors": ["Jane Smith"], "year": 2020, "has_pdf": False}
    return base | fields


async def _import(session, data: bytes):
    return await workspace_package.import_package(session, data)


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


def _pdf_files(pdf_dir) -> list:
    return sorted(p.name for p in pdf_dir.rglob("*") if p.is_file()) if pdf_dir.exists() else []


# ---- Review Focus 1: round trip ----


async def test_round_trip_recreates_workspace_papers_notes_highlights_and_tags(session, pdf_dir, jobs):
    ws, alpha, beta, human, ai = await _seeded(session, pdf_dir)
    data = await workspace_package.export_package(session, ws.id, pdfs=True)
    package = data.read()
    await workspaces.delete(session, ws.id)
    for paper in (alpha, beta):
        await papers.delete_paper(session, paper.id)
    report = await _import(session, package)
    assert (report.name, report.added, report.matched, report.notes, report.pdfs_skipped) == (
        "Sleep review",
        2,
        0,
        2,
        0,
    )
    new = await session.get(Workspace, report.workspace_id)
    assert (new.research_question, new.inclusion_criteria, new.exclusion_criteria) == (
        "Does sleep help?",
        "RCTs",
        "Animal studies",
    )
    assert new.description.splitlines()[0] == "Night-time studies"
    assert new.description.splitlines()[-1].startswith("Imported from a PaperLab package made on ")
    rows = {p.title: p for p in await workspaces.papers(session, report.workspace_id)}
    assert rows["Alpha study"].doi == "10.1/alpha" and rows["Alpha study"].pmid == "111"
    assert rows["Alpha study"].has_pdf and open(rows["Alpha study"].file_path, "rb").read() == SEEDED_PDF
    assert not rows["Beta study"].has_pdf and rows["Beta study"].details_source == "crossref"
    view = {n.body: n for n in await workspaces.notes(session, report.workspace_id)}
    assert (view["Key finding"].provenance, view["Key finding"].color) == ("human", "#ff0000")
    assert view["Key finding"].anchors[0].page == 1
    assert view["Key finding"].anchors[0].bbox == [(10.0, 20.0, 100.0, 40.0)]
    assert view["Key finding"].anchors[0].quoted_text == "the quoted line"
    assert view["An AI summary"].provenance == "llm_edited" and view["An AI summary"].kind == "summary"
    tagged = await tags.paper_tag_map(session, report.workspace_id)
    assert tagged == {rows["Alpha study"].id: ["Core"]}
    assert ("ingest_paper", str(rows["Alpha study"].id)) in jobs.jobs
    assert ("ingest_paper", str(rows["Beta study"].id)) not in jobs.jobs


async def test_the_screening_record_is_kept_for_download(session, pdf_dir, client):
    ws, *_ = await _seeded(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=False)).read()
    report = await _import(session, package)
    response = await client.get(f"/api/workspaces/{report.workspace_id}/package-record")
    assert response.status_code == 200 and set(response.json()) == {"screening", "prisma"}
    plain = await client.get(f"/api/workspaces/{ws.id}/package-record")
    assert plain.status_code == 404


# ---- Review Focus 2: matching an existing library ----


async def test_papers_already_in_the_library_are_matched_not_duplicated(session, pdf_dir, jobs):
    doi_paper = await papers.create_metadata_paper(
        session, {"title": f"By doi {RUN}", "doi": f"10.9/doi.{RUN}"}, "crossref"
    )
    oa_paper = await papers.create_metadata_paper(
        session, {"title": f"By openalex {RUN}", "openalex_id": f"W{RUN}"}, "openalex"
    )
    pmid_paper = await papers.create_metadata_paper(session, {"title": f"By pmid {RUN}", "pmid": f"9{RUN}"}, "crossref")
    pmc_paper = await papers.create_metadata_paper(
        session, {"title": f"By pmcid {RUN}", "pmcid": f"PMC{RUN}"}, "crossref"
    )
    title_paper = await papers.create_metadata_paper(
        session, {"title": f"Same title {RUN}", "authors": ["Jane Smith"], "year": 2020}, "crossref"
    )
    before = await _count(session, Paper)
    # the title match needs the same title, authors and year as the library paper
    package = _package(
        papers=[
            _paper("p1", "By doi", doi=f"10.9/doi.{RUN}"),
            _paper("p2", "By openalex", openalex_id=f"W{RUN}"),
            _paper("p3", "By pmid", pmid=f"9{RUN}"),
            _paper("p4", "By pmcid", pmcid=f"PMC{RUN}"),
            {"key": "p5", "title": f"Same title {RUN}", "authors": ["Jane Smith"], "year": 2020, "has_pdf": False},
        ],
        notes=[
            {
                "key": f"n{i}",
                "body": f"note {i}",
                "provenance": "human",
                "color": "#facc15",
                "kind": None,
                "created_at": None,
                "updated_at": None,
                "papers": [f"p{i}"],
                "highlights": [],
            }
            for i in range(1, 6)
        ],
    )
    report = await _import(session, package)
    assert (report.added, report.matched, report.notes) == (0, 5, 5)
    assert await _count(session, Paper) == before
    linked = {
        pid: set(await session.scalars(select(note_papers.c.note_id).where(note_papers.c.paper_id == pid)))
        for pid in (doi_paper.id, oa_paper.id, pmid_paper.id, pmc_paper.id, title_paper.id)
    }
    assert all(len(notes_on) == 1 for notes_on in linked.values())
    member = await session.scalars(
        select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == report.workspace_id)
    )
    assert set(member) == set(linked)
    assert jobs.jobs == []


async def test_a_package_paper_matched_by_identifier_is_added_only_once(session, pdf_dir):
    package = _package(
        papers=[_paper("p1", "Twice", doi=f"10.7/twice.{RUN}"), _paper("p2", "Twice again", doi=f"10.7/twice.{RUN}")]
    )
    report = await _import(session, package)
    assert (report.added, report.matched) == (1, 0)
    assert await session.scalar(select(func.count()).select_from(Paper).where(Paper.doi == f"10.7/twice.{RUN}")) == 1


# ---- Review Focus 3: a hostile package is refused, and nothing is written ----


async def _refused(session, pdf_dir, data: bytes, code: str):
    with pytest.raises(InvalidInput, match=code):
        await _import(session, data)
    assert (
        await session.scalar(select(func.count()).select_from(Workspace).where(Workspace.name == "Imported review"))
        == 0
    )
    assert _pdf_files(pdf_dir) == []


async def test_a_zip_with_parent_or_absolute_paths_is_unsafe(session, pdf_dir):
    for bad in ("../escape.txt", "/etc/escape.txt"):
        data = _zip({"manifest.json": b"{}", bad: b"x"})
        await _refused(session, pdf_dir, data, "package_unsafe")


async def test_a_symlink_member_is_unsafe(session, pdf_dir):
    link = zipfile.ZipInfo("manifest.json")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    data = _zip({"target.txt": b"x"}, extra=[link])
    await _refused(session, pdf_dir, data, "package_unsafe")


async def test_more_than_twenty_thousand_members_is_unsafe(session, pdf_dir):
    members = {f"f{i}.txt": b"" for i in range(20_001)}
    await _refused(session, pdf_dir, _zip(members), "package_unsafe")


async def test_an_unknown_format_or_a_newer_version_is_refused(session, pdf_dir):
    await _refused(session, pdf_dir, _package(format_name="other-thing"), "package_unknown_format")
    await _refused(session, pdf_dir, _package(version=2), "package_unknown_format")
    await _refused(session, pdf_dir, b"not a zip at all", "package_unknown_format")


async def test_json_over_twenty_megabytes_is_too_large(session, pdf_dir):
    manifest = json.dumps(
        {
            "format": "paperlab-workspace",
            "format_version": 1,
            "created_at": "2026-11-01",
            "workspace": {"name": "Imported review"},
        }
    )
    padded = b'{"papers": []}' + b" " * (20 * 1024 * 1024 + 1)
    data = _zip(
        {
            "manifest.json": manifest.encode(),
            "papers.json": padded,
            "notes.json": b'{"notes": []}',
            "tags.json": b'{"tags": []}',
            "screening.json": b"{}",
            "prisma.json": b"{}",
        }
    )
    await _refused(session, pdf_dir, data, "package_too_large")


async def test_a_fake_pdf_is_skipped_and_counted_and_the_paper_is_kept(session, pdf_dir, jobs):
    package = _package(
        papers=[_paper("p1", "Fake PDF", has_pdf=True, pdf="pdfs/p1.pdf")], pdfs={"p1": b"this is not a pdf"}
    )
    report = await _import(session, package)
    assert (report.added, report.pdfs_skipped) == (1, 1)
    paper = (await workspaces.papers(session, report.workspace_id))[0]
    assert paper.file_path is None and paper.status == PaperStatus.READY
    assert not [p for p in _pdf_files(pdf_dir) if p.endswith(".pdf")]
    assert jobs.jobs == []


async def test_a_pdf_over_the_upload_cap_is_skipped(session, pdf_dir, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_UPLOAD_PDF_BYTES", 10)
    package = _package(papers=[_paper("p1", "Too big", has_pdf=True, pdf="pdfs/p1.pdf")], pdfs={"p1": PDF})
    report = await _import(session, package)
    assert (report.added, report.pdfs_skipped) == (1, 1)


# ---- Review Focus 5: names ----


async def test_a_taken_name_gets_a_number(session, pdf_dir):
    await workspaces.create(session, "Imported review")
    first = await _import(session, _package(name="Imported review"))
    second = await _import(session, _package(name="Imported review"))
    assert (first.name, second.name) == ("Imported review (2)", "Imported review (3)")


async def test_an_imported_workspace_is_a_normal_workspace_with_the_import_line(session, pdf_dir):
    report = await _import(session, _package(name="Field notes", description="Mine"))
    ws = await session.get(Workspace, report.workspace_id)
    assert ws.description.startswith("Mine\nImported from a PaperLab package made on 2026-11-01.")


# ---- all or nothing ----


async def test_a_failure_partway_leaves_no_workspace_no_paper_and_no_pdf(session, pdf_dir, monkeypatch):
    package = _package(
        papers=[_paper("p1", "First", has_pdf=True, pdf="pdfs/p1.pdf"), _paper("p2", "Second")], pdfs={"p1": PDF}
    )
    calls = {"n": 0}
    real = workspace_package._new_paper

    async def fail_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return await real(*args, **kwargs)

    monkeypatch.setattr(workspace_package, "_new_paper", fail_second)
    papers_before = await _count(session, Paper)
    with pytest.raises(RuntimeError):
        await _import(session, package)
    assert calls["n"] == 2
    assert not [p for p in _pdf_files(pdf_dir) if p.endswith(".pdf")]
    assert await _count(session, Paper) == papers_before
    assert (
        await session.scalar(select(func.count()).select_from(Workspace).where(Workspace.name == "Imported review"))
        == 0
    )


async def test_a_failing_write_removes_the_pdfs_it_wrote(session, pdf_dir, monkeypatch):
    package = _package(papers=[_paper("p1", "Written", has_pdf=True, pdf="pdfs/p1.pdf")], pdfs={"p1": PDF})

    async def refuse(*_):
        raise RuntimeError("queue down")

    monkeypatch.setattr(queue, "enqueue", refuse)
    with pytest.raises(RuntimeError):
        await _import(session, package)
    assert not [p for p in _pdf_files(pdf_dir) if p.endswith(".pdf")]


# ---- the API ----


async def test_the_api_imports_a_package_and_reports_the_fixed_counts(client, session, pdf_dir):
    package = _package(papers=[_paper("p1", "Api paper", doi=f"10.4/api.{RUN}")], name="Api import")
    response = await client.post(
        "/api/workspaces/import-package", files={"file": ("api.paperlab", package, "application/zip")}
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["added"], body["matched"], body["notes"], body["pdfs_skipped"]) == (
        "Api import",
        1,
        0,
        0,
        0,
    )


async def test_the_api_refuses_an_unknown_format_with_its_code(client, session):
    response = await client.post(
        "/api/workspaces/import-package",
        files={"file": ("x.paperlab", _package(format_name="nope"), "application/zip")},
    )
    assert response.status_code == 422 and response.json()["detail"] == "package_unknown_format"


async def test_deleting_a_workspace_removes_its_package_record(session, pdf_dir):
    space = await workspaces.create(session, f"Record {uuid.uuid4().hex[:8]}")
    record = workspace_package.record_path(space.id)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("{}")

    await workspaces.delete(session, space.id)

    assert not record.exists()
