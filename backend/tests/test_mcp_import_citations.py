"""M40 Task 9a: import_citations over MCP — a path or the raw text, the same caps, and polling a job."""

import json
import uuid

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call
from test_citations_import_api import FakeJobRedis, bib, title

from app.core import citations_import_apply as cia
from app.core import citations_import_run as run
from app.core import queue, workspaces

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]
RUN = uuid.uuid4().hex[:8]


def result(response) -> dict:
    """The tool's answer (mcp_fixtures.result would unwrap its own `result` field)."""
    assert not response.is_error, response.structured_content or response.content
    return response.structured_content


@pytest.fixture(autouse=True)
def redis(monkeypatch) -> FakeJobRedis:
    fake = FakeJobRedis()
    monkeypatch.setattr(queue, "_pool", fake)
    return fake


async def test_a_file_path_imports_inline_into_a_workspace(session, tmp_path, redis):
    name = f"MCP import {RUN}"
    await workspaces.create(session, name)
    path = tmp_path / "refs.bib"
    path.write_bytes(bib("m1"))

    out = result(await call("import_citations", path_or_text=str(path), workspace=name, fetch_free_pdfs=False))

    assert out["state"] == "finished" and out["job_id"] is None
    [entry] = out["result"]["needs_pdf"]
    assert (entry["title"], entry["pages"], entry["tags"]) == (title("m1"), "45-67", ["alpha", "beta"])
    assert redis.jobs == []


async def test_raw_text_imports_inline(session, redis):
    out = result(await call("import_citations", path_or_text=bib("m2").decode(), fetch_free_pdfs=False))
    assert [n["title"] for n in out["result"]["needs_pdf"]] == [title("m2")]


async def test_a_missing_path_says_so(session):
    response = await call("import_citations", path_or_text="/nowhere/refs.bib")
    assert response.is_error and response.structured_content["error"] == "file_not_found"


async def test_an_unreadable_text_is_a_plain_error(session):
    response = await call("import_citations", path_or_text="@article{broken, title={")
    assert response.is_error and response.structured_content["error"] == "invalid_input"
    assert isinstance(response.structured_content["detail"], str)


async def test_the_caps_hold_for_a_path_before_reading_it(session, tmp_path, monkeypatch):
    monkeypatch.setattr(run, "FILE_MAX_BYTES", 100)
    path = tmp_path / "big.bib"
    path.write_bytes(bib("m3"))
    monkeypatch.setattr(type(path), "read_bytes", lambda self: pytest.fail("read an oversize file"))

    response = await call("import_citations", path_or_text=str(path))

    assert response.is_error and response.structured_content["detail"] == run.too_big("big.bib")


async def test_the_caps_hold_for_raw_text(session, monkeypatch):
    monkeypatch.setattr(run, "FILE_MAX_BYTES", 100)
    response = await call("import_citations", path_or_text=bib("m4").decode())
    assert response.is_error and response.structured_content["detail"] == run.too_big("references")


async def test_an_unknown_workspace_answers_with_the_names(session):
    response = await call("import_citations", path_or_text=bib("m5").decode(), workspace=f"Nope {RUN}")
    assert response.is_error and response.structured_content["error"] == "unknown_workspace"


async def test_a_fetching_import_is_a_job_to_poll_with_job_id(session, redis):
    queued = result(await call("import_citations", path_or_text=bib("m6", doi=True).decode()))
    assert queued["state"] == "queued"
    job_id = queued["job_id"]
    assert [job[0] for job in redis.jobs] == [cia.JOB]

    assert result(await call("import_citations", job_id=job_id))["state"] == "queued"
    redis.start(job_id)
    await redis.set(cia.progress_key(job_id), json.dumps(cia.progress_payload(cia.ImportResult(), 1, False)))
    assert result(await call("import_citations", job_id=job_id))["state"] == "running"
    redis.finish(job_id, cia.progress_payload(cia.ImportResult(imported=1), 1, True))
    done = result(await call("import_citations", job_id=job_id))
    assert done["state"] == "finished" and done["result"]["imported"] == 1
    assert result(await call("import_citations", job_id="nope"))["state"] == "expired"


async def test_neither_a_file_nor_a_job_is_refused(session):
    response = await call("import_citations")
    assert response.is_error and response.structured_content["error"] == "path_or_text_or_job_id_required"
