"""The reporting-guideline checklist tools through an in-process client, on the test's rolled-back session."""

import uuid

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result

from app.core import manuscripts

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


async def created():
    return result(await call("create_manuscript", title="Draft"))


def failed(response, code):
    assert response.is_error
    assert response.structured_content["error"] == code, response.structured_content
    return response.structured_content


async def test_get_and_set_round_trip():
    mid = (await created())["id"]
    empty = result(await call("get_manuscript_checklist", manuscript_id=mid))
    assert empty["guideline"] is None and empty["done"] == 0
    assert [g["id"] for g in empty["available"]] == ["prisma2020", "strobe", "consort", "ml"]
    got = result(await call("set_manuscript_checklist", manuscript_id=mid, guideline="ml", tick=["data.splits"]))
    assert (got["guideline"], got["done"], got["total"]) == ("ml", 1, 18)
    assert result(await call("set_manuscript_checklist", manuscript_id=mid, untick=["data.splits"]))["done"] == 0


async def test_get_does_not_write(session):
    mid = (await created())["id"]
    before = (await manuscripts.get(session, uuid.UUID(mid))).updated_at
    result(await call("get_manuscript_checklist", manuscript_id=mid))
    assert (await manuscripts.get(session, uuid.UUID(mid))).updated_at == before
    assert not (session.new or session.dirty or session.deleted)


async def test_choosing_ticks_nothing_and_final_steps_survive(session):
    mid = (await created())["id"]
    await manuscripts.update(session, uuid.UUID(mid), checklist={"Submit": True})
    result(await call("set_manuscript_checklist", manuscript_id=mid, guideline="strobe"))
    assert (await manuscripts.get(session, uuid.UUID(mid))).checklist == {"Submit": True, "guideline": "strobe"}


async def test_ticks_set_through_the_patch_route_are_seen(client):
    mid = (await created())["id"]
    patched = await client.patch(
        f"/api/manuscripts/{mid}", json={"checklist": {"guideline": "ml", "ml:eval.runs": True}}
    )
    assert patched.status_code == 200
    got = result(await call("get_manuscript_checklist", manuscript_id=mid))
    assert got["done"] == 1 and [i["id"] for i in got["items"] if i["ticked"]] == ["eval.runs"]


async def test_unknown_ids_are_recoverable_errors():
    mid = (await created())["id"]
    err = failed(await call("set_manuscript_checklist", manuscript_id=mid, guideline="ml", tick=["99"]), "unknown_item")
    assert err["available"][0] == "data.source"
    failed(await call("set_manuscript_checklist", manuscript_id=mid, guideline="nope"), "unknown_guideline")
    failed(await call("get_manuscript_checklist", manuscript_id=uuid.uuid4()), "unknown_manuscript")
