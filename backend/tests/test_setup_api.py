"""The first-run setup's flag over HTTP (spec §5, R9). The dev database's own row says done (the owner's library has
papers); each test changes it only inside its rolled-back transaction."""

import pytest
from sqlalchemy import delete

from app.models import Setup

# One row: tests that write it wait on each other's transactions, so they share one xdist worker.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("setup")]


async def test_finish_and_skip_mark_setup_done_and_tests_can_set_it_back(client):
    assert (await client.put("/api/setup", json={"done": False})).json() == {"done": False}
    assert (await client.get("/api/setup")).json() == {"done": False}

    assert (await client.put("/api/setup", json={"done": True})).json() == {"done": True}
    assert (await client.get("/api/setup")).json() == {"done": True}


@pytest.mark.parametrize("body", [{}, {"done": "yes"}, {"done": 1}, {"done": None}, {"done": True, "step": 2}])
async def test_anything_but_one_boolean_is_refused(client, body):
    response = await client.put("/api/setup", json=body)

    assert response.status_code == 422


async def test_without_its_row_setup_is_not_done_and_a_put_writes_the_row(client, session):
    await session.execute(delete(Setup))

    assert (await client.get("/api/setup")).json() == {"done": False}
    assert (await client.put("/api/setup", json={"done": True})).json() == {"done": True}
    assert (await session.get(Setup, True, populate_existing=True)).done is True
