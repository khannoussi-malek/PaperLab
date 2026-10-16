"""M63 upload_paper: a PDF Claude already has, as base64, filed like an upload in the app."""

import base64
import uuid

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import func, select

from app.core import pipeline, workspaces
from app.models import Paper

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]
RUN = uuid.uuid4().hex[:8]
PDF = b"%PDF-1.7\n%an uploaded paper\n"


def b64(data: bytes = PDF) -> str:
    return base64.b64encode(data).decode()


async def make_ws(session, label: str) -> str:
    name = f"Upload {label} {RUN}"
    await workspaces.create(session, name)
    return name


async def paper_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Paper))


async def test_upload_paper_queues_ingest_files_and_tags_it(session, jobs, pdf_dir):
    ws = await make_ws(session, "ok")

    added = result(await call("upload_paper", workspace=ws, filename="My Paper.pdf", pdf_base64=b64(), tags=["a", "b"]))

    assert added["status"] == "queued" and added["title"] == "My Paper"
    assert jobs.jobs == [("ingest_paper", added["paper_id"])]
    assert (pdf_dir / f"{added['paper_id']}.pdf").read_bytes() == PDF
    listed = result(await call("list_papers", workspace=ws, tags=["a"]))
    assert [r["id"] for r in listed] == [added["paper_id"]]
    assert [r["id"] for r in result(await call("list_papers", workspace=ws, tags=["b"]))] == [added["paper_id"]]


async def test_oversize_is_refused_before_decoding(session, jobs, pdf_dir, monkeypatch):
    ws = await make_ws(session, "big")
    before = await paper_count(session)
    monkeypatch.setattr(pipeline.base64, "b64decode", lambda *a, **k: pytest.fail("decoded an oversize upload"))
    huge = "A" * (4 * -(-pipeline.MAX_UPLOAD_PDF_BYTES // 3) + 8)

    response = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=huge)

    assert response.is_error and response.structured_content["error"] == "pdf_too_large"
    assert response.structured_content["max_mb"] == 30
    assert await paper_count(session) == before and jobs.jobs == [] and list(pdf_dir.glob('*')) == []


async def test_decoded_size_over_the_cap_is_refused(session, jobs, pdf_dir, monkeypatch):
    ws = await make_ws(session, "cap")
    monkeypatch.setattr(pipeline, "MAX_UPLOAD_PDF_BYTES", 10)
    response = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=b64(PDF + b"x" * 20))
    assert response.is_error and response.structured_content["error"] == "pdf_too_large"
    assert jobs.jobs == [] and list(pdf_dir.glob('*')) == []


async def test_invalid_base64_and_non_pdf_are_refused(session, jobs, pdf_dir):
    ws = await make_ws(session, "bad")
    before = await paper_count(session)

    bad64 = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64="not base64 !!")
    not_pdf = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=b64(b"<html>hi</html>"))

    assert bad64.is_error and bad64.structured_content["error"] == "invalid_base64"
    assert not_pdf.is_error and not_pdf.structured_content["error"] == "not_a_pdf"
    assert await paper_count(session) == before and jobs.jobs == [] and list(pdf_dir.glob('*')) == []


async def test_a_known_doi_reuses_the_library_paper(session, jobs, pdf_dir):
    ws = await make_ws(session, "dup")
    existing = Paper(title="Already here", file_path="x.pdf", doi="10.1234/known")
    session.add(existing)
    await session.commit()
    before = await paper_count(session)

    added = result(
        await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=b64(), doi="10.1234/KNOWN", tags=["t"])
    )

    assert added["status"] == "already_in_library" and added["paper_id"] == str(existing.id)
    assert await paper_count(session) == before and jobs.jobs == [] and list(pdf_dir.glob('*')) == []
    listed = result(await call("list_papers", workspace=ws, tags=["t"]))
    assert [r["id"] for r in listed] == [str(existing.id)]


async def test_a_new_doi_is_kept_on_the_paper(session, jobs):
    ws = await make_ws(session, "doi")
    added = result(await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=b64(), doi="10.1234/Fresh"))

    paper = await session.get(Paper, uuid.UUID(added["paper_id"]))
    assert added["status"] == "queued" and paper.doi == "10.1234/fresh" and "doi" in paper.manual_fields


async def test_bad_tag_name_refuses_before_writing(session, jobs, pdf_dir):
    ws = await make_ws(session, "tag")
    before = await paper_count(session)
    response = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=b64(), tags=["ok", "x" * 200])
    assert response.is_error and response.structured_content["error"] == "invalid_tag_name"
    assert await paper_count(session) == before and jobs.jobs == [] and list(pdf_dir.glob('*')) == []
