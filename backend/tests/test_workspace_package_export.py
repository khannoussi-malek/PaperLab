"""M35a Task 1: a workspace exports as one .paperlab file (Review Focus 4: no secret, server path or database id)."""

import io
import json
import uuid
import zipfile

import pytest
from sqlalchemy import select

from app.config import settings
from app.core import notes, papers, prisma_export, tags, workspace_package, workspaces
from app.core.errors import NotFound
from app.core.notes import Anchor
from app.models import LLMConnection, Note, PaperSources, Workspace, note_papers
from app.models.workspace_search import SearchRunEligibility
from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7 package export test"
SECRET_KEY = "sk-SECRET-KEY-m35"
SECRET_HOST = "http://secret-host.example:9999"
SECRET_EMAIL = "owner-secret@example.org"


async def _export(session, workspace_id, *, pdfs: bool) -> zipfile.ZipFile:
    file = await workspace_package.export_package(session, workspace_id, pdfs=pdfs)
    return zipfile.ZipFile(io.BytesIO(file.read()))


def _json(zf: zipfile.ZipFile, name: str):
    return json.loads(zf.read(name))


async def _seeded(session, pdf_dir):
    """A workspace with a PDF paper, a details-only paper, a note with a highlight, an AI note and a tag."""
    ws = await workspaces.create(session, "Sleep review", description="Night-time studies")
    model = await session.get(Workspace, ws.id)
    model.research_question = "Does sleep help?"
    model.inclusion_criteria = "RCTs"
    model.exclusion_criteria = "Animal studies"
    alpha = await papers.create_paper(
        session,
        "alpha.pdf",
        PDF,
        pdf_dir,
        prefill={"title": "Alpha study", "doi": "10.1/alpha", "pmid": "111", "authors": ["Jane Smith"], "year": 2020},
    )
    beta = await papers.create_metadata_paper(
        session, {"title": "Beta study", "doi": "10.1/beta", "authors": ["Hans Muller"], "year": 2021}, "crossref"
    )
    for paper in (alpha, beta):
        await workspaces.add_paper(session, ws.id, paper.id)
    human = await notes.create_human_note(
        session, "Key finding", Anchor(alpha.id, 1, [(10.0, 20.0, 100.0, 40.0)], "the quoted line"), color="#ff0000"
    )
    ai = Note(body="An AI summary", provenance="llm_edited", kind="summary")
    session.add(ai)
    await session.flush()
    await notes._link(session, ai.id, [alpha.id])
    await session.commit()
    await tags.tag_papers(session, ws.id, "Core", paper_ids=[alpha.id])
    return ws, alpha, beta, human, ai


async def test_manifest_names_the_format_and_the_workspace(session, pdf_dir):
    ws, *_ = await _seeded(session, pdf_dir)
    zf = await _export(session, ws.id, pdfs=False)
    manifest = _json(zf, "manifest.json")
    assert manifest["format"] == "paperlab-workspace" and manifest["format_version"] == 1
    assert isinstance(manifest["paperlab_version"], str) and manifest["created_at"]
    assert manifest["workspace"] == {
        "name": "Sleep review",
        "description": "Night-time studies",
        "research_question": "Does sleep help?",
        "inclusion_criteria": "RCTs",
        "exclusion_criteria": "Animal studies",
    }
    assert manifest["counts"] == {"papers": 2, "notes": 2, "pdfs": 0}


async def test_papers_are_keyed_and_carry_their_details(session, pdf_dir):
    ws, alpha, beta, *_ = await _seeded(session, pdf_dir)
    zf = await _export(session, ws.id, pdfs=False)
    rows = {row["title"]: row for row in _json(zf, "papers.json")["papers"]}
    assert sorted(row["key"] for row in rows.values()) == ["p1", "p2"]
    assert rows["Alpha study"]["doi"] == "10.1/alpha" and rows["Alpha study"]["pmid"] == "111"
    assert rows["Alpha study"]["authors"] == ["Jane Smith"] and rows["Alpha study"]["year"] == 2020
    assert rows["Alpha study"]["has_pdf"] is True and "pdf" not in rows["Alpha study"]
    assert rows["Beta study"]["has_pdf"] is False
    assert all("file_path" not in row and "id" not in row for row in rows.values())


async def test_notes_keep_provenance_colour_kind_and_highlights(session, pdf_dir):
    ws, alpha, *_ = await _seeded(session, pdf_dir)
    zf = await _export(session, ws.id, pdfs=False)
    papers_json = {row["title"]: row["key"] for row in _json(zf, "papers.json")["papers"]}
    by_body = {row["body"]: row for row in _json(zf, "notes.json")["notes"]}
    human = by_body["Key finding"]
    assert (human["provenance"], human["color"], human["kind"]) == ("human", "#ff0000", None)
    assert human["papers"] == [papers_json["Alpha study"]]
    assert human["highlights"] == [
        {
            "paper": papers_json["Alpha study"],
            "page": 1,
            "rects": [[10.0, 20.0, 100.0, 40.0]],
            "quoted_text": "the quoted line",
        }
    ]
    assert by_body["An AI summary"]["provenance"] == "llm_edited"
    assert by_body["An AI summary"]["kind"] == "summary"
    assert all(note["created_at"] and note["updated_at"] for note in by_body.values())


async def test_tags_land_on_the_right_papers(session, pdf_dir):
    ws, *_ = await _seeded(session, pdf_dir)
    zf = await _export(session, ws.id, pdfs=False)
    papers_json = {row["title"]: row["key"] for row in _json(zf, "papers.json")["papers"]}
    assert _json(zf, "tags.json")["tags"] == [{"name": "Core", "papers": [papers_json["Alpha study"]]}]


async def test_screening_and_prisma_match_prisma_export(session):
    ws, hits = await make_pool(session, [("first abstract", "relevant"), ("second abstract", "not_relevant")])
    hits[0].suggestion, hits[0].suggestion_model, hits[0].suggestion_reason = (
        "exclude",
        "Ollama · qwen3:8b",
        "wrong_topic",
    )
    await session.flush()
    expected = await prisma_export.prisma_export(session, ws.id, None)
    zf = await _export(session, ws.id, pdfs=False)
    prisma = _json(zf, "prisma.json")
    assert (prisma["identified"], prisma["stage1_screened"], prisma["stage1_excluded"]) == (
        expected.identified,
        expected.stage1_screened,
        expected.stage1_excluded,
    )
    assert prisma["sought"] == expected.sought and prisma["included"] == expected.included
    assert [run["key"] for run in prisma["runs"]] == ["r1"] and "id" not in prisma["runs"][0]
    screening = _json(zf, "screening.json")
    assert screening["runs"][0]["query"] == "q" and screening["runs"][0]["key"] == "r1"
    assert len(screening["hits"]) == 2
    suggested = next(h for h in screening["hits"] if h["ai_suggestion"])
    assert suggested["ai_suggestion"]["ai"] is True and suggested["ai_suggestion"]["model"] == "Ollama · qwen3:8b"
    assert suggested["stage1"]["status"] == "relevant" and suggested["run"] == "r1"


async def test_stage2_verdicts_are_listed_per_hit(session):
    ws, hits = await make_pool(session, [("only abstract", "relevant")])
    paper = await papers.create_metadata_paper(session, {"title": "Gamma", "doi": "10.1/gamma"}, "crossref")
    await workspaces.add_paper(session, ws.id, paper.id)
    hits[0].paper_id = paper.id
    session.add(SearchRunEligibility(paper_id=paper.id, search_run_id=hits[0].run_id, stage2_status="include"))
    await session.flush()
    zf = await _export(session, ws.id, pdfs=False)
    [hit] = _json(zf, "screening.json")["hits"]
    assert hit["stage2"] == {"status": "include", "exclude_reason": None} and hit["paper"] == "p1"


async def test_pdfs_only_when_asked(session, pdf_dir):
    ws, *_ = await _seeded(session, pdf_dir)
    without = await _export(session, ws.id, pdfs=False)
    assert not [name for name in without.namelist() if name.startswith("pdfs/")]
    with_pdfs = await _export(session, ws.id, pdfs=True)
    rows = {row["title"]: row for row in _json(with_pdfs, "papers.json")["papers"]}
    member = rows["Alpha study"]["pdf"]
    assert member == f"pdfs/{rows['Alpha study']['key']}.pdf" and with_pdfs.read(member) == PDF
    assert "pdf" not in rows["Beta study"]
    assert [n for n in with_pdfs.namelist() if n.startswith("pdfs/")] == [member]
    assert _json(with_pdfs, "manifest.json")["counts"]["pdfs"] == 1


async def test_no_secret_server_path_or_database_id_in_the_zip(session, pdf_dir):  # Review Focus 4
    ws, alpha, beta, human, ai = await _seeded(session, pdf_dir)
    session.add(LLMConnection(kind="anthropic", label="m35 secret", base_url=SECRET_HOST, api_key=SECRET_KEY))
    sources = await session.get(PaperSources, True)
    if sources is None:
        sources = PaperSources(id=True)
        session.add(sources)
    sources.openalex_api_key, sources.contact_email = SECRET_KEY, SECRET_EMAIL
    await session.flush()
    ids = [str(x) for x in (ws.id, alpha.id, beta.id, human.id, ai.id)]
    zf = await _export(session, ws.id, pdfs=True)
    forbidden = [SECRET_KEY, SECRET_HOST, SECRET_EMAIL, str(settings.pdf_dir), "/data/", *ids]
    for name in zf.namelist():
        data = zf.read(name)
        for needle in forbidden:
            assert needle.encode() not in data, f"{needle!r} leaked into {name}"


async def test_the_download_route_serves_the_package(client, session, pdf_dir):
    ws, *_ = await _seeded(session, pdf_dir)
    response = await client.get(f"/api/workspaces/{ws.id}/package", params={"pdfs": "true"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="sleep-review.paperlab"'
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    assert "manifest.json" in zf.namelist() and any(n.startswith("pdfs/") for n in zf.namelist())


async def test_an_unknown_workspace_is_not_found(session):
    with pytest.raises(NotFound):
        await workspace_package.export_package(session, uuid.uuid4(), pdfs=False)


async def test_a_paper_link_outside_the_workspace_is_not_exported(session, pdf_dir):
    ws, alpha, beta, human, _ = await _seeded(session, pdf_dir)
    outside = await papers.create_metadata_paper(session, {"title": "Outside paper", "doi": "10.1/out"}, "crossref")
    await notes._link(session, human.id, [outside.id])
    await session.commit()
    zf = await _export(session, ws.id, pdfs=False)
    assert "Outside paper" not in zf.read("papers.json").decode()
    assert "10.1/out" not in zf.read("notes.json").decode()
    linked = await session.scalars(select(note_papers.c.paper_id).where(note_papers.c.note_id == human.id))
    assert outside.id in set(linked)
