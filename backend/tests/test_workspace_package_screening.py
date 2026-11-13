"""M35c Task 2: a v2 package's screening imports as live search runs, decisions and eligibility (Review Focus 1-5)."""

import io
import json
import zipfile

import pytest
from conftest import FakeArq
from sqlalchemy import func, select

from app.core import papers, prisma_export, queue, workspace_package, workspace_search, workspaces
from app.core.errors import Conflict, InvalidInput
from app.models import Paper, Workspace
from app.models.references import ExternalRef
from app.models.workspace_search import (
    SearchRunEligibility,
    WorkspaceSearchCursor,
    WorkspaceSearchHit,
    WorkspaceSearchRun,
)
from app.workers import workspace_search as search_worker
from tests.test_workspace_package_export import SECRET_EMAIL, SECRET_KEY, _json, screened
from tests.test_workspace_package_import import _package

pytestmark = pytest.mark.anyio

PRISMA_TOTALS = (
    "identified", "identified_databases", "duplicates_removed", "stage1_screened", "stage1_excluded",
    "stage1_excluded_by_reason", "sought", "not_retrieved", "stage2_assessed", "stage2_excluded",
    "stage2_excluded_by_reason", "included", "citation_searching",
)  # fmt: skip


@pytest.fixture(autouse=True)
def jobs(monkeypatch) -> FakeArq:
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


def _rewrite(package: bytes, changes: dict[str, bytes]) -> bytes:
    """The same zip with some members replaced (a tampered package)."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            dst.writestr(name, changes.get(name, src.read(name)))
    return out.getvalue()


async def _counts(session) -> tuple[int, ...]:
    return tuple(
        [
            await session.scalar(select(func.count()).select_from(model))
            for model in (Workspace, Paper, WorkspaceSearchHit, WorkspaceSearchRun, ExternalRef, SearchRunEligibility)
        ]
    )


async def test_an_export_and_import_give_identical_prisma_counts(session, pdf_dir):  # Review Focus 1
    ws, rows = await screened(session, pdf_dir)
    before = await prisma_export.prisma_export(session, ws.id, None)
    assert (before.included, before.not_retrieved, before.stage2_excluded) == (1, 1, 0)  # not vacuous
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    for paper in rows["alpha"], rows["beta"], rows["gamma"]:
        await papers.delete_paper(session, paper.id)
    report = await workspace_package.import_package(session, package)
    after = await prisma_export.prisma_export(session, report.workspace_id, None)
    for field in PRISMA_TOTALS:
        assert getattr(after, field) == getattr(before, field), field
    members = {p.title for p in await workspaces.papers(session, report.workspace_id)}
    assert members == {"Alpha study", "Beta study"}  # gamma is a paper the screening names, not a member
    hit = await session.scalar(
        select(WorkspaceSearchHit).where(
            WorkspaceSearchHit.workspace_id == report.workspace_id, WorkspaceSearchHit.snowball_round == 1
        )
    )
    assert hit.paper_id is not None and hit.seed_paper_id is not None


async def test_the_imported_runs_cursors_and_hits_keep_their_state(session, pdf_dir):
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    report = await workspace_package.import_package(session, package)
    runs = (
        await session.scalars(select(WorkspaceSearchRun).where(WorkspaceSearchRun.workspace_id == report.workspace_id))
    ).all()
    assert {r.query_text for r in runs} == {"sleep trial", 'Snowball from "Alpha study"'}
    assert all(r.status == "exhausted" and r.saved_search_id is None for r in runs)
    database = next(r for r in runs if r.query_text == "sleep trial")
    assert database.query_overrides_json == {"crossref": "sleep RCT"}
    assert database.stats_json["per_source_raw_count"] == {"openalex": 3, "crossref": 2}
    assert SECRET_KEY not in str(database.stats_json)
    cursors = (
        await session.scalars(
            select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id.in_([r.id for r in runs]))
        )
    ).all()
    assert cursors and all(c.exhausted for c in cursors)
    assert {c.source: c.last_error for c in cursors}["crossref"] == "timed out for mailto=***"
    hits = (
        await session.scalars(select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == report.workspace_id))
    ).all()
    by_title = {h.normalized_title: h for h in hits}
    alpha = by_title["alpha study"]
    assert (alpha.stage1_status, alpha.suggestion, alpha.suggestion_model, alpha.acquisition_status) == (
        "relevant",
        "include",
        "Ollama · qwen3:8b",
        "imported",
    )
    assert (alpha.suggestion_quotes, alpha.suggestion_prompt_version) == ([{"quote": "sleep", "section": "Results"}], 3)
    assert by_title["beta study"].stage1_exclude_reason == "wrong_topic"
    assert by_title["delta study"].stage1_status == "maybe" and by_title["delta study"].paper_id is None


async def test_the_reference_already_in_the_library_is_reused(session, pdf_dir):  # Review Focus 2
    ws, rows = await screened(session, pdf_dir)
    alpha_ref = await session.scalar(select(ExternalRef).where(ExternalRef.title == "Alpha study"))
    alpha_ref.external_ids = {"openalex": "W123"}  # a unique index on this id: a plain insert would collide
    await session.commit()
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    refs_before = await session.scalar(select(func.count()).select_from(ExternalRef))
    originals = (
        await session.scalars(select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == ws.id))
    ).all()
    original_ref = {hit.normalized_title: hit.external_ref_id for hit in originals}
    report = await workspace_package.import_package(session, package)
    # Alpha and Beta carry identifiers and are found again. Delta has none, and the find-or-create rule (as in a
    # search) can't match a title alone, so it gets its own reference: the one new row.
    assert await session.scalar(select(func.count()).select_from(ExternalRef)) == refs_before + 1
    hits = (
        await session.scalars(select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == report.workspace_id))
    ).all()
    assert len(hits) == len(originals) == 4
    reused = {hit.normalized_title: hit.external_ref_id for hit in hits}
    assert reused["alpha study"] == original_ref["alpha study"]
    assert reused["beta study"] == original_ref["beta study"]
    assert reused["delta study"] != original_ref["delta study"]


async def test_an_imported_screening_is_inert(session, pdf_dir):  # Review Focus 3
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    report = await workspace_package.import_package(session, package)
    workspace = await session.get(Workspace, report.workspace_id)
    assert workspace.read_only is True and workspace.suggest_status == "idle"
    run = (
        await session.scalars(
            select(WorkspaceSearchRun).where(
                WorkspaceSearchRun.workspace_id == report.workspace_id, WorkspaceSearchRun.query_text == "sleep trial"
            )
        )
    ).one()
    hits_before = await session.scalar(select(func.count()).select_from(WorkspaceSearchHit))
    await search_worker.run_workspace_search({}, str(run.id))  # the worker: a run that isn't running does nothing
    await session.refresh(run)
    assert run.status == "exhausted"
    assert await session.scalar(select(func.count()).select_from(WorkspaceSearchHit)) == hits_before
    with pytest.raises(Conflict, match="workspace_read_only"):
        await workspace_search.continue_run(session, report.workspace_id, run.id)
    await workspaces.make_editable(session, report.workspace_id)
    with pytest.raises(Conflict, match="nothing_left_to_fetch"):
        await workspace_search.continue_run(session, report.workspace_id, run.id)


async def test_an_older_package_keeps_its_record_and_gets_no_screening(session, pdf_dir):  # Review Focus 4
    data = _package(name="Old review")
    report = await workspace_package.import_package(session, data)
    assert report.has_record is True
    assert await session.scalar(select(func.count()).select_from(WorkspaceSearchRun)) == 0
    assert workspace_package.read_record(report.workspace_id) is not None


async def test_tampered_counts_are_package_invalid_and_nothing_is_written(session, pdf_dir):  # Review Focus 5
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    screening = _json(zipfile.ZipFile(io.BytesIO(package)), "screening.json")
    alpha = next(h for h in screening["hits"] if h["title"] == "Alpha study")
    alpha["stage1"] = {"status": "not_relevant", "exclude_reason": "other", "note": None}
    tampered = _rewrite(package, {"screening.json": json.dumps(screening).encode()})
    before, files_before = await _counts(session), sorted(p.name for p in pdf_dir.rglob("*") if p.is_file())
    with pytest.raises(InvalidInput) as refused:
        await workspace_package.import_package(session, tampered)
    assert str(refused.value) == "package_invalid"
    assert refused.value.details == {"detail": "screening counts don't match"}
    assert await _counts(session) == before
    assert sorted(p.name for p in pdf_dir.rglob("*") if p.is_file()) == files_before


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s["hits"][0].update(stage1={"status": "bogus", "exclude_reason": None, "note": None}),
        lambda s: s["hits"][0].update(run="r99"),
        lambda s: s["runs"][0]["stats"].update(snowball=["not", "a", "dict"]),
        lambda s: s["branches"].append(
            {"hit": None, "paper": None, "state": "stopped", "directions": [], "reason": None, "set_by": "owner"}
        ),
    ],
    ids=[
        "a stage-1 value outside the check",
        "a hit naming no run",
        "snowball stats of the wrong type",
        "a branch naming no target",
    ],
)
async def test_a_screening_outside_the_package_shape_is_package_invalid(session, pdf_dir, edit):
    ws, _ = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    screening = _json(zipfile.ZipFile(io.BytesIO(package)), "screening.json")
    edit(screening)
    tampered = _rewrite(package, {"screening.json": json.dumps(screening).encode()})
    with pytest.raises(InvalidInput) as refused:
        await workspace_package.import_package(session, tampered)
    assert str(refused.value) == "package_invalid"


async def test_a_package_without_pdfs_imports_and_its_decisions_still_match(session, pdf_dir):
    """Without the PDFs a retrieved paper has no full text on import, so the retrieval totals can't be reproduced and
    aren't checked; the decision totals still are, and the package imports."""
    ws, rows = await screened(session, pdf_dir)
    before = await prisma_export.prisma_export(session, ws.id, None)
    package = (await workspace_package.export_package(session, ws.id, pdfs=False)).read()
    await workspaces.delete(session, ws.id)
    for paper in rows["alpha"], rows["beta"], rows["gamma"]:
        await papers.delete_paper(session, paper.id)
    report = await workspace_package.import_package(session, package)
    after = await prisma_export.prisma_export(session, report.workspace_id, None)
    assert (after.identified, after.sought, after.stage1_excluded) == (
        before.identified,
        before.sought,
        before.stage1_excluded,
    )
    assert after.included == 0 and after.not_retrieved == before.sought  # no full text here, so none retrieved


async def test_the_import_report_counts_the_search_results_rebuilt(session, pdf_dir):
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    report = await workspace_package.import_package(session, package)
    assert report.hits == 4


async def test_a_v1_package_reports_no_search_results(session, pdf_dir):
    report = await workspace_package.import_package(session, _package(name="Old review"))
    assert report.hits == 0


def _screening_of(package: bytes) -> dict:
    return _json(zipfile.ZipFile(io.BytesIO(package)), "screening.json")


def _is_alpha(hit: dict) -> bool:
    return hit["title"] == "Alpha study"


async def test_an_import_never_edits_a_library_reference(session, pdf_dir):  # M1
    ws, rows = await screened(session, pdf_dir)
    alpha_ref = await session.scalar(select(ExternalRef).where(ExternalRef.title == "Alpha study"))
    alpha_ref.external_ids = {"openalex": "W123"}
    alpha_ref.abstract = "The library's own abstract"
    await session.commit()
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    alpha_ref.abstract = None  # blank in the library now; the package's hit carries an abstract
    await session.commit()
    await workspaces.delete(session, ws.id)
    await workspace_package.import_package(session, package)
    await session.refresh(alpha_ref)
    assert alpha_ref.abstract is None
    assert alpha_ref.external_ids == {"openalex": "W123"}


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: next(h for h in s["hits"] if h["ai_suggestion"])["ai_suggestion"].update(suggested_at="yesterday"),
        lambda s: s["eligibility"][0].update(assessed_at="yesterday"),
        lambda s: s["runs"][0].update(started_at="2026-11-01T10:00:00"),
        lambda s: next(h for h in s["hits"] if h["ai_suggestion"])["ai_suggestion"].update(prompt_version=40000),
        lambda s: s["hits"][0].update(year=2**40),
        lambda s: s["hits"][0].update(snowball_round=2**40),
        lambda s: s["runs"][0]["stats"].update(per_source_raw_count=[1, 2]),
        lambda s: s["runs"][0]["stats"].update(failed_sources="openalex"),
        lambda s: s["runs"][0]["cursors"][0]["cursor"].update(errors="many"),
        lambda s: s["links"][0].update(parent_hit=s["links"][0]["child_hit"], parent_paper=None),
    ],
    ids=[
        "an AI suggestion's time that is no timestamp",
        "an eligibility time that is no timestamp",
        "a run start with no time zone",
        "a prompt version past smallint",
        "a year past int4",
        "a snowball round past int4",
        "per-source counts that are a list",
        "failed sources that are text",
        "a cursor's error count that is text",
        "a hit linked to itself",
    ],
)
async def test_a_screening_value_the_database_cannot_hold_is_package_invalid(session, pdf_dir, edit):  # M2, L2
    ws, _ = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    screening = _screening_of(package)
    edit(screening)
    tampered = _rewrite(package, {"screening.json": json.dumps(screening).encode()})
    before = await _counts(session)
    with pytest.raises(InvalidInput) as refused:
        await workspace_package.import_package(session, tampered)
    assert str(refused.value) == "package_invalid"
    assert await _counts(session) == before


async def test_a_count_check_that_cannot_run_is_package_invalid(session, pdf_dir, monkeypatch):  # M2
    ws, _ = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)

    async def broken(*args, **kwargs):
        raise RuntimeError("the rebuilt screening cannot be read back")

    monkeypatch.setattr(prisma_export, "prisma_export", broken)
    before = await _counts(session)
    with pytest.raises(InvalidInput) as refused:
        await workspace_package.import_package(session, package)
    assert str(refused.value) == "package_invalid"
    assert refused.value.details == {"detail": "screening counts don't match"}
    assert await _counts(session) == before


async def test_the_full_text_totals_are_checked_when_the_package_carries_the_pdfs(session, pdf_dir):  # M3
    ws, _ = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    prisma = _json(zipfile.ZipFile(io.BytesIO(package)), "prisma.json")
    tampered = _rewrite(package, {"prisma.json": json.dumps(prisma | {"included": prisma["included"] + 1}).encode()})
    with pytest.raises(InvalidInput) as refused:
        await workspace_package.import_package(session, tampered)
    assert refused.value.details == {"detail": "screening counts don't match"}


async def test_the_full_text_totals_follow_the_package_not_the_library(session, pdf_dir):  # M3
    ws, rows = await screened(session, pdf_dir)
    alpha, pdf_path = rows["alpha"], rows["alpha"].file_path
    alpha.file_path = None  # the owner's copy has no full text, so alpha counts as not retrieved
    await session.commit()
    package = (await workspace_package.export_package(session, ws.id, pdfs=False)).read()
    await workspaces.delete(session, ws.id)
    for paper in rows["beta"], rows["gamma"]:
        await papers.delete_paper(session, paper.id)
    alpha.file_path = pdf_path  # the importing library holds alpha with its own PDF
    await session.commit()
    report = await workspace_package.import_package(session, package)
    assert report.hits == 4


async def test_a_hit_on_a_reference_an_earlier_hit_uses_gets_its_own_copy(session, pdf_dir):  # M4
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    screening = _screening_of(package)
    alpha = next(h for h in screening["hits"] if _is_alpha(h))
    # A second database hit on the same paper (same DOI): the owner's dedupe kept both, and the importer's library
    # holds one reference for them. Its prisma duplicates_removed is one more than the first hit's alone.
    twin = alpha | {
        "key": "h99", "source_method": "database_search",
        "stage1": {"status": None, "exclude_reason": None, "note": None},
        "stage1_decided_at": None, "paper": None, "stage2": None, "ai_suggestion": None,
        "acquisition_status": "not_attempted", "seed_paper": None, "snowball_round": None,
        "priority": None, "topic_fit": None,
    }  # fmt: skip
    prisma = _json(zipfile.ZipFile(io.BytesIO(package)), "prisma.json")
    changes = {
        "screening.json": json.dumps(screening | {"hits": screening["hits"] + [twin]}).encode(),
        "prisma.json": json.dumps(prisma | {"duplicates_removed": prisma["duplicates_removed"] - 1}).encode(),
    }
    tampered = _rewrite(package, changes)
    alpha_ref = await session.scalar(select(ExternalRef).where(ExternalRef.title == "Alpha study"))
    await workspaces.delete(session, ws.id)
    report = await workspace_package.import_package(session, tampered)
    assert report.hits == 5
    hits = (
        await session.scalars(
            select(WorkspaceSearchHit).where(
                WorkspaceSearchHit.workspace_id == report.workspace_id,
                WorkspaceSearchHit.normalized_title == "alpha study",
            )
        )
    ).all()
    assert len(hits) == 2
    refs = {hit.external_ref_id for hit in hits}
    assert alpha_ref.id in refs and len(refs) == 2
    copy = await session.get(ExternalRef, next(r for r in refs if r != alpha_ref.id))
    assert (copy.title, copy.doi, copy.external_ids) == ("Alpha study", "10.1/alpha", {})


async def test_a_snowball_seed_error_is_redacted_in_the_package(session, pdf_dir):  # L1
    ws, _ = await screened(session, pdf_dir)
    run = await session.scalar(
        select(WorkspaceSearchRun).where(
            WorkspaceSearchRun.workspace_id == ws.id, WorkspaceSearchRun.query_text.like("Snowball%")
        )
    )
    snowball = run.stats_json["snowball"]
    seed = {
        **snowball["seeds"][0],
        "error": f"timed out for mailto={SECRET_EMAIL}",
        "errors": {"cites": f"HTTP 503 mailto={SECRET_EMAIL}"},
    }
    run.stats_json = {**run.stats_json, "snowball": {**snowball, "seeds": [seed]}}
    await session.commit()
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    assert SECRET_EMAIL not in json.dumps(_screening_of(package))
    out = next(r for r in _screening_of(package)["runs"] if r["query"].startswith("Snowball"))["stats"]["snowball"][
        "seeds"
    ][0]
    assert out["error"] == "timed out for mailto=***"
    assert out["errors"] == {"cites": "HTTP 503 mailto=***"}


async def test_nul_characters_are_stripped_from_imported_strings(session, pdf_dir):  # L3
    ws, _ = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    manifest = _json(zipfile.ZipFile(io.BytesIO(package)), "manifest.json")
    manifest["workspace"]["name"] = "Sleep\u0000 review"
    tampered = _rewrite(package, {"manifest.json": json.dumps(manifest).encode()})
    report = await workspace_package.import_package(session, tampered)
    assert (await session.get(Workspace, report.workspace_id)).name == "Sleep review"


async def test_a_held_paper_without_its_pdf_skips_the_full_text_compare_and_is_not_refused(session, pdf_dir):
    ws, rows = await screened(session, pdf_dir)
    package = (await workspace_package.export_package(session, ws.id, pdfs=True)).read()
    await workspaces.delete(session, ws.id)
    for paper in rows["alpha"], rows["beta"], rows["gamma"]:  # this library keeps the papers, but not their PDFs
        held = await session.get(Paper, paper.id)
        held.file_path = None
    await session.flush()

    report = await workspace_package.import_package(session, package)  # an import never changes a matched paper

    assert report.hits > 0
    for paper in rows["alpha"], rows["beta"]:
        assert (await session.get(Paper, paper.id)).file_path is None
