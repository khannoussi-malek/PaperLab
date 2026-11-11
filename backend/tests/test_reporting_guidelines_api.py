import pytest

from app.core import queue

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def test_list_guidelines(client):
    body = (await client.get("/api/reporting-guidelines")).json()
    assert [g["id"] for g in body] == ["prisma2020", "strobe", "consort", "ml"]
    assert all(g["items"] and g["label"] and g["applies_to"] for g in body)


async def test_an_incomplete_checklist_never_blocks_compile(client, arq):
    m = (await client.post("/api/manuscripts", json={"title": "D", "template": "article"})).json()
    patch = await client.patch(
        f"/api/manuscripts/{m['id']}", json={"checklist": {"guideline": "prisma2020", "prisma2020:1": True}}
    )
    assert patch.status_code == 200 and patch.json()["checklist"]["prisma2020:1"] is True
    compiled = await client.post(f"/api/manuscripts/{m['id']}/compile")
    assert compiled.status_code == 202 and arq.jobs[0][0] == "compile_manuscript"
