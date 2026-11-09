import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result

from app.core import manuscript_templates, manuscripts

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


async def test_create_stores_the_template(client):
    r = await client.post("/api/manuscripts", json={"title": "D", "template": "ieee"})
    assert r.status_code == 201 and r.json()["template"] == "ieee"
    got = (await client.get(f"/api/manuscripts/{r.json()['id']}")).json()
    assert got["template"] == "ieee"
    listed = (await client.get("/api/manuscripts", params={"orphans": True})).json()
    assert next(m["template"] for m in listed if m["id"] == r.json()["id"]) == "ieee"


async def test_unknown_template_still_refused(client):
    r = await client.post("/api/manuscripts", json={"title": "D", "template": "nope"})
    assert r.status_code == 422


async def test_create_from_files_is_custom(session):
    m = await manuscripts.create_from_files(session, title="Imp", workspace_id=None,
                                            files={"main.tex": "x"}, main_file="main.tex")
    assert m.template == "custom"


async def test_create_from_template_function_stores_name(session):
    m = await manuscripts.create(session, title="T", template="lncs", workspace_id=None)
    assert m.template == "lncs"


@pytest.mark.parametrize("name", list(manuscript_templates.TEMPLATES))
async def test_mcp_create_accepts_every_template(name):
    """If a template is added to the data but not to the tool's Literal, this fails."""
    created = result(await call("create_manuscript", title="D", template=name))
    assert created["main_file"] == "main.tex"
