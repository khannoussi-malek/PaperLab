"""M35b1: an imported workspace is read-only until its owner makes it editable.

Every workspace write answers 409 workspace_read_only, in core, API and MCP alike. Reading, chat, exports, the package
record and delete stay allowed. Make it editable clears the flag for good; an import is the only thing that sets it.
"""

import base64
import uuid

import pytest
from conftest import FakeArq
from mcp_fixtures import *  # noqa: F403 - the MCP tests' autouse fixtures (in-process server, offline sources)
from mcp_fixtures import call, result
from screening_pool import make_pool
from sqlalchemy import update
from test_chat_workspace_api import make_paper, make_workspace, query_model  # noqa: F401 - fixture for chat

from app.api.deps import get_discovery
from app.core import papers, queue, saved_searches, schedules, tags, workspace_package, workspace_search, workspaces
from app.core.errors import Conflict, NotFound
from app.models import Workspace
from tests.test_workspace_package_import import _package, _paper

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:8]
PDF = b"%PDF-1.4 read-only test PDF"
BIB = b"@article{member, title={Member}, doi={10.7777/read-only-member}}\n"
LOCKED = "workspace_read_only"


@pytest.fixture(autouse=True)
def jobs(monkeypatch) -> FakeArq:
    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    return pool


async def _workspace(session, *, read_only: bool) -> dict:
    """A workspace with one member paper, one tag, a search run with one hit and a saved search. Flagged read-only
    last, once the fixtures are in place (the guard would refuse building them)."""
    ws, hits = await make_pool(session, [("An abstract about sleep", None)])
    details = {"title": f"Member {RUN}", "doi": f"10.7777/{uuid.uuid4().hex}", "authors": ["Jane Smith"], "year": 2020}
    paper = await papers.create_metadata_paper(session, details, "crossref")
    await workspaces.add_paper(session, ws.id, paper.id)
    await tags.tag_papers(session, ws.id, "Core", paper_ids=[paper.id])
    tag = (await tags.resolve(session, ws.id, ["Core"]))[0]
    saved = await saved_searches.create(
        session, ws.id, query="sleep", schedule=schedules.to_cron("daily", time="02:00"), timezone="UTC"
    )
    if read_only:
        await session.execute(update(Workspace).where(Workspace.id == ws.id).values(read_only=True))
        await session.commit()
    return {
        "ws": ws.id, "name": ws.name, "paper": paper.id, "doi": paper.doi, "tag": tag.id, "run": hits[0].run_id,
        "hit": hits[0].id, "saved": saved.id,
    }  # fmt: skip


def _detail(response):
    body = response.json() if response.content else None
    return body.get("detail") if isinstance(body, dict) else None


# ---- core: the guard and the flag ----


async def test_require_writable_refuses_a_read_only_workspace_and_names_no_one_else(session, pdf_dir):
    locked, open_ = await _workspace(session, read_only=True), await _workspace(session, read_only=False)
    with pytest.raises(Conflict) as refused:
        await workspaces.require_writable(session, locked["ws"])
    assert str(refused.value) == LOCKED
    assert await workspaces.require_writable(session, open_["ws"]) is None


async def test_require_writable_is_not_found_for_an_unknown_workspace(session):
    with pytest.raises(NotFound):
        await workspaces.require_writable(session, uuid.uuid4())


async def test_a_core_write_on_a_read_only_workspace_is_refused(session, pdf_dir):
    locked = await _workspace(session, read_only=True)
    with pytest.raises(Conflict):
        await workspaces.rename(session, locked["ws"], "Renamed")
    with pytest.raises(Conflict):
        await tags.tag_papers(session, locked["ws"], "Other", paper_ids=[locked["paper"]])
    with pytest.raises(Conflict):
        await tags.rename_by_id(session, locked["ws"], locked["tag"], "Other")
    with pytest.raises(Conflict):
        await workspace_search.clear_hits(session, locked["ws"])


async def test_make_editable_clears_the_flag_for_good(session, pdf_dir):
    locked = await _workspace(session, read_only=True)
    view = await workspaces.make_editable(session, locked["ws"])
    assert view.read_only is False
    await workspaces.rename(session, locked["ws"], "Renamed after all")
    assert (await workspaces.make_editable(session, locked["ws"])).read_only is False  # idempotent
    with pytest.raises(NotFound):
        await workspaces.make_editable(session, uuid.uuid4())


async def test_a_normal_create_is_editable_and_the_list_says_so(session, pdf_dir):
    view = await workspaces.create(session, f"Plain {RUN}")
    assert view.read_only is False
    locked = await _workspace(session, read_only=True)
    listed = {v.id: v.read_only for v in await workspaces.list_workspaces(session)}
    assert listed[locked["ws"]] is True and listed[view.id] is False


# ---- API: every guarded route ----

# (method, path, body): {ws}, {paper}, {doi}, {tag}, {run}, {hit}, {saved} are the fixture's ids. A body is valid for
# the route, so a 409 can only come from the guard, and each route that is not guarded is left out on purpose.
GUARDED_ROUTES = [
    ("PATCH", "/api/workspaces/{ws}", {"json": {"name": "Renamed workspace"}}),
    ("PUT", "/api/workspaces/{ws}/papers/{paper}", {}),
    ("DELETE", "/api/workspaces/{ws}/papers/{paper}", {}),
    ("PATCH", "/api/workspaces/{ws}/papers/{paper}/eligibility?run={run}", {"json": {"status": "include"}}),
    ("POST", "/api/workspaces/{ws}/tags/apply", {"json": {"tag": "Core", "paper_ids": ["{paper}"]}}),
    ("POST", "/api/workspaces/{ws}/tags/remove", {"json": {"tag": "Core", "paper_ids": ["{paper}"]}}),
    ("PATCH", "/api/workspaces/{ws}/tags/{tag}", {"json": {"new_name": "Renamed tag"}}),
    ("DELETE", "/api/workspaces/{ws}/tags/{tag}", {}),
    ("POST", "/api/workspaces/{ws}/search/runs", {"json": {"query": "sleep", "sources": ["openalex"]}}),
    ("POST", "/api/workspaces/{ws}/search/runs/{run}", {}),
    ("POST", "/api/workspaces/{ws}/search/runs/{run}/stop", {}),
    ("PUT", "/api/workspaces/{ws}/search/screening", {"json": {"research_question": "Does sleep help?"}}),
    ("POST", "/api/workspaces/{ws}/search/suggestions", {"json": {}}),
    ("POST", "/api/workspaces/{ws}/search/suggestions/stop", {}),
    ("POST", "/api/workspaces/{ws}/search/hits/accept-suggestions", {"json": {"hit_ids": ["{hit}"]}}),
    ("DELETE", "/api/workspaces/{ws}/search/hits", {}),
    ("PATCH", "/api/workspaces/{ws}/search/hits/bulk", {"json": {"hit_ids": ["{hit}"], "stage1_status": "relevant"}}),
    ("PATCH", "/api/workspaces/{ws}/search/hits/{hit}", {"json": {"stage1_status": "relevant"}}),
    ("POST", "/api/workspaces/{ws}/search/hits/{hit}/suggest", {"json": {}}),
    ("POST", "/api/workspaces/{ws}/search/hits/import", {"json": {"hit_ids": []}}),
    ("POST", "/api/workspaces/{ws}/search/hits/{hit}/upload", {"files": {"file": ("hit.pdf", PDF, "application/pdf")}}),
    ("POST", "/api/workspaces/{ws}/search/snowball", {"json": {"seed_paper_ids": ["{paper}"], "seed_hit_ids": []}}),
    ("POST", "/api/workspaces/{ws}/search/snowball-next/run", {}),
    (
        "PUT",
        "/api/workspaces/{ws}/search/branch",
        {"json": {"hit_id": "{hit}", "state": "go_further", "directions": ["cites"]}},
    ),
    (
        "POST",
        "/api/workspaces/{ws}/saved-searches",
        {"json": {"query": "sleep", "schedule_kind": "daily", "time": "02:00", "timezone": "UTC"}},
    ),  # noqa: E501
    ("PATCH", "/api/workspaces/{ws}/saved-searches/{saved}", {"json": {"query": "sleep again"}}),
    ("DELETE", "/api/workspaces/{ws}/saved-searches/{saved}", {}),
    ("POST", "/api/workspaces/{ws}/saved-searches/{saved}/run", {}),
    ("POST", "/api/workspaces/{ws}/evidence-cards", {"json": {}}),
    (
        "POST",
        "/api/citations/import",
        {
            "files": {"file": ("refs.bib", BIB, "text/plain")},
            "data": {"workspace_id": "{ws}", "fetch_free_pdfs": "false"},
        },
    ),  # noqa: E501
    (
        "POST",
        "/api/papers",
        {"files": {"file": ("paper.pdf", PDF, "application/pdf")}, "data": {"workspace_id": "{ws}"}},
    ),  # noqa: E501
    (
        "POST",
        "/api/discovery/add",
        {"json": {"candidate": {"title": "Member", "doi": "{doi}"}, "workspace_id": "{ws}"}},
    ),  # noqa: E501
]


def _fill(value, ids: dict):
    """The route's body or form with the fixture's ids in place of the {placeholders}, recursively."""
    if isinstance(value, dict):
        return {key: _fill(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, ids) for item in value]
    if isinstance(value, tuple):
        return tuple(_fill(item, ids) for item in value)
    if isinstance(value, str):
        return value.format(**{key: str(item) for key, item in ids.items()})
    return value


def _request(path: str, spec: dict, ids: dict) -> tuple[str, dict]:
    return _fill(path, ids), _fill(spec, ids)


@pytest.fixture
def offline_discovery(app, discovery_fakes):
    """The discovery route's provider offline. Its candidate is already in the library, so no source is asked."""
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers


GUARDED_IDS = [f"{method} {path}" for method, path, _ in GUARDED_ROUTES]


@pytest.mark.parametrize("method, path, spec", GUARDED_ROUTES, ids=GUARDED_IDS)
async def test_every_guarded_route_answers_409_on_a_read_only_workspace(
    client, session, pdf_dir, offline_discovery, method, path, spec
):
    ids = await _workspace(session, read_only=True)
    url, kwargs = _request(path, spec, ids)
    response = await client.request(method, url, **kwargs)
    assert response.status_code == 409, response.text
    assert _detail(response) == LOCKED


@pytest.mark.parametrize("method, path, spec", GUARDED_ROUTES, ids=GUARDED_IDS)
async def test_every_guarded_route_still_works_on_a_normal_workspace(
    client, session, pdf_dir, offline_discovery, discovery_fakes, method, path, spec
):
    ids = await _workspace(session, read_only=False)
    for direction in ("references", "citations"):  # a snowball seed asks Semantic Scholar; it has no hits to give
        discovery_fakes.s2.reply(f"/graph/v1/paper/DOI:{ids['doi']}/{direction}", 200, json={"data": []})
    url, kwargs = _request(path, spec, ids)
    response = await client.request(method, url, **kwargs)
    assert response.status_code < 500, response.text
    assert _detail(response) != LOCKED


# ---- API: what stays allowed ----


async def test_reads_and_exports_still_work_on_a_read_only_workspace(client, session, pdf_dir):
    ids = await _workspace(session, read_only=True)
    ws = str(ids["ws"])
    for path in (
        f"/api/workspaces/{ws}/papers", f"/api/workspaces/{ws}/tags", f"/api/workspaces/{ws}/notes",
        f"/api/workspaces/{ws}/search/runs", f"/api/workspaces/{ws}/search/screening",
        f"/api/workspaces/{ws}/saved-searches", f"/api/workspaces/{ws}/chat",
        f"/api/workspaces/{ws}/citations?format=bibtex", f"/api/workspaces/{ws}/citations.zip?format=bibtex",
        f"/api/workspaces/{ws}/notes.zip", f"/api/workspaces/{ws}/package",
        f"/api/workspaces/{ws}/package-record/exists",
    ):  # fmt: skip
        response = await client.get(path)
        assert response.status_code == 200, (path, response.text)


async def test_delete_still_works_on_a_read_only_workspace(client, session, pdf_dir):
    ids = await _workspace(session, read_only=True)
    response = await client.delete(f"/api/workspaces/{ids['ws']}")
    assert response.status_code == 204


async def test_chat_still_answers_a_read_only_workspace(client, session, pdf_dir, fake_llm, query_model):  # noqa: F811
    paper = await make_paper(session, "Read-only chat")
    workspace = await make_workspace(session, [paper])
    await session.execute(update(Workspace).where(Workspace.id == workspace.id).values(read_only=True))
    await session.commit()
    response = await client.post(f"/api/workspaces/{workspace.id}/chat", json={"question": "What is it?"})
    assert response.status_code == 200


async def test_the_api_make_editable_clears_the_flag_and_writes_work_again(client, session, pdf_dir):
    ids = await _workspace(session, read_only=True)
    ws = str(ids["ws"])
    response = await client.post(f"/api/workspaces/{ws}/make-editable")
    assert response.status_code == 200
    assert response.json()["read_only"] is False
    renamed = await client.patch(f"/api/workspaces/{ws}", json={"name": "Renamed after all"})
    assert renamed.status_code == 200
    assert renamed.json()["read_only"] is False


async def test_make_editable_of_an_unknown_workspace_is_not_found(client, session):
    response = await client.post(f"/api/workspaces/{uuid.uuid4()}/make-editable")
    assert response.status_code == 404


async def test_the_api_lists_read_only_on_each_workspace(client, session, pdf_dir):
    locked = await _workspace(session, read_only=True)
    listed = {row["id"]: row["read_only"] for row in (await client.get("/api/workspaces")).json()}
    assert listed[str(locked["ws"])] is True


# ---- an import sets it ----


async def test_an_import_makes_a_read_only_workspace_that_keeps_its_record(client, session, pdf_dir):
    """A version 1 package (no live screening): its record is kept. A version 2 package keeps none (its screening is
    live, see test_workspace_package_screening)."""
    report = await workspace_package.import_package(session, _package(name=f"Locked {uuid.uuid4().hex[:6]}"))
    ws = await session.get(Workspace, report.workspace_id)
    assert ws.read_only is True

    late = {"title": "Late", "doi": f"10.7777/{uuid.uuid4().hex}"}
    paper = await papers.create_metadata_paper(session, late, "crossref")
    response = await client.put(f"/api/workspaces/{report.workspace_id}/papers/{paper.id}")
    assert response.status_code == 409 and _detail(response) == LOCKED
    assert (await client.get(f"/api/workspaces/{report.workspace_id}/package-record/exists")).json() == {"exists": True}


async def test_an_imported_package_is_read_only_when_it_arrives_over_the_api(client, session, pdf_dir):
    package = _package(papers=[_paper("p1", "Api read-only", doi=f"10.4/ro.{RUN}")], name=f"Api ro {RUN}")
    response = await client.post(
        "/api/workspaces/import-package", files={"file": ("ro.paperlab", package, "application/zip")}
    )
    assert response.status_code == 201
    assert (await session.get(Workspace, uuid.UUID(response.json()["workspace_id"]))).read_only is True


# ---- MCP: every workspace write tool ----

MCP_WRITES = [
    pytest.param(
        "tag_papers", lambda i: {"workspace": i["name"], "tag": "Core", "paper_ids": [str(i["paper"])]}, id="tag_papers"
    ),  # noqa: E501
    pytest.param(
        "untag_papers",
        lambda i: {"workspace": i["name"], "tag": "Core", "paper_ids": [str(i["paper"])]},
        id="untag_papers",
    ),  # noqa: E501
    pytest.param(
        "rename_tag", lambda i: {"workspace": i["name"], "tag": "Core", "new_name": "Renamed"}, id="rename_tag"
    ),  # noqa: E501
    pytest.param("delete_tag", lambda i: {"workspace": i["name"], "tag": "Core"}, id="delete_tag"),
    pytest.param(
        "add_paper_to_workspace",
        lambda i: {"workspace": i["name"], "paper_id": str(i["paper"])},
        id="add_paper_to_workspace",
    ),  # noqa: E501
    pytest.param(
        "remove_paper_from_workspace",
        lambda i: {"workspace": i["name"], "paper_id": str(i["paper"])},
        id="remove_paper_from_workspace",
    ),  # noqa: E501
    pytest.param("add_paper", lambda i: {"identifier": "10.7777/not-fetched", "workspace": i["name"]}, id="add_paper"),
    pytest.param(
        "add_papers", lambda i: {"identifiers": ["10.7777/not-fetched"], "workspace": i["name"]}, id="add_papers"
    ),  # noqa: E501
    pytest.param(
        "upload_paper",
        lambda i: {"workspace": i["name"], "filename": "a.pdf", "pdf_base64": base64.b64encode(PDF).decode()},
        id="upload_paper",
    ),  # noqa: E501
    pytest.param(
        "import_citations", lambda i: {"path_or_text": BIB.decode(), "workspace": i["name"]}, id="import_citations"
    ),  # noqa: E501
    pytest.param(
        "start_search_run",
        lambda i: {"workspace": i["name"], "query": "sleep", "sources": ["openalex"]},
        id="start_search_run",
    ),  # noqa: E501
    pytest.param("stop_search_run", lambda i: {"run_id": str(i["run"])}, id="stop_search_run"),
    pytest.param("continue_search_run", lambda i: {"run_id": str(i["run"])}, id="continue_search_run"),
    pytest.param(
        "set_screening_criteria",
        lambda i: {"workspace": i["name"], "research_question": "Does sleep help?"},
        id="set_screening_criteria",
    ),  # noqa: E501
    pytest.param("run_prescreen", lambda i: {"workspace": i["name"]}, id="run_prescreen"),
    pytest.param("enrich_hits", lambda i: {"workspace": i["name"]}, id="enrich_hits"),
    pytest.param("stop_prescreen", lambda i: {"workspace": i["name"]}, id="stop_prescreen"),
    pytest.param(
        "accept_suggestions", lambda i: {"workspace": i["name"], "hit_ids": [str(i["hit"])]}, id="accept_suggestions"
    ),  # noqa: E501
    pytest.param(
        "review_hits",
        lambda i: {"workspace": i["name"], "hit_ids": [str(i["hit"])], "decision": "relevant"},
        id="review_hits",
    ),  # noqa: E501
    pytest.param("import_hit", lambda i: {"workspace": i["name"], "hit_id": str(i["hit"])}, id="import_hit"),
    pytest.param(
        "snowball",
        lambda i: {"workspace": i["name"], "seed_paper_ids": [str(i["paper"])], "direction": "both"},
        id="snowball",
    ),  # noqa: E501
    pytest.param(
        "set_eligibility",
        lambda i: {"workspace": i["name"], "paper_id": str(i["paper"]), "run_id": str(i["run"]), "verdict": "include"},
        id="set_eligibility",
    ),  # noqa: E501
    pytest.param("create_saved_search", lambda i: {"workspace": i["name"], "query": "sleep"}, id="create_saved_search"),  # noqa: E501
    pytest.param(
        "set_saved_search_enabled",
        lambda i: {"saved_search_id": str(i["saved"]), "enabled": False},
        id="set_saved_search_enabled",
    ),  # noqa: E501
]


@pytest.mark.parametrize("tool, arguments", MCP_WRITES)
async def test_every_mcp_write_tool_answers_workspace_read_only(session, pdf_dir, tool, arguments):
    ids = await _workspace(session, read_only=True)
    response = await call(tool, **arguments(ids))
    assert response.is_error, (tool, response.content)
    assert response.structured_content["error"] == LOCKED


async def test_an_mcp_read_still_works_on_a_read_only_workspace(session, pdf_dir):
    ids = await _workspace(session, read_only=True)
    listed = result(await call("list_papers", workspace=ids["name"]))
    assert [row["id"] for row in listed] == [str(ids["paper"])]
    assert result(await call("list_tags", workspace=ids["name"]))[0]["name"] == "Core"
