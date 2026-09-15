import uuid

import pytest

from app.models import Paper

pytestmark = pytest.mark.anyio

REGION = [70.0, 60.0, 290.0, 240.0]


async def make_paper(session) -> Paper:
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", page_count=9)
    session.add(paper)
    await session.commit()
    return paper


async def own_data(client, name="My runs") -> dict:
    grid = {"columns": [{"name": "Run"}, {"name": "F1"}], "rows": [{"cells": [{"raw": "mine"}, {"raw": "92.0"}]}]}
    return (await client.post("/api/datasets", json={"name": name, "kind": "user", "grid": grid})).json()


async def captured_table(client, paper: Paper) -> dict:
    cell = {"page": 7, "bbox": [[72, 100, 90, 110]]}
    cells = [{"raw": "BERT-L", "extracted": "BERT-L", **cell}, {"raw": "90.9", "extracted": "90.9", **cell}]
    grid = {"columns": [{"name": "System"}, {"name": "F1"}], "rows": [{"cells": cells}]}
    body = {"name": "Table 2", "kind": "table", "paper_id": str(paper.id), "page": 7, "region": REGION, "grid": grid}
    return (await client.post("/api/datasets", json=body)).json()


def bar(*datasets: dict) -> dict:
    return {"type": "bar", "series": [
        {"id": f"s{i}", "dataset_id": d["id"], "x": d["columns"][0]["id"], "y": d["columns"][1]["id"]}
        for i, d in enumerate(datasets)
    ]}  # fmt: skip


async def test_chart_lifecycle_over_http(client):
    mine = await own_data(client)

    created = await client.post("/api/charts", json={"title": "F1", "spec": bar(mine)})
    assert created.status_code == 201
    chart = created.json()
    assert (chart["title"], chart["spec_version"], chart["note_ids"]) == ("F1", 1, [])
    assert chart["spec"]["series"][0]["y"] == mine["columns"][1]["id"]
    assert chart["spec"]["layout"] == {"barmode": "group", "facet": "none", "facet_columns": 2}
    assert (await client.get(f"/api/charts/{chart['id']}")).json() == chart
    [summary] = [c for c in (await client.get("/api/charts")).json() if c["id"] == chart["id"]]
    assert (summary["type"], summary["sources"], summary["note_count"]) == ("bar", ["My data"], 0)

    renamed = await client.patch(f"/api/charts/{chart['id']}", json={"title": "Dev F1"})
    assert (renamed.status_code, renamed.json()["title"], renamed.json()["spec"]) == (200, "Dev F1", chart["spec"])
    as_line = await client.patch(f"/api/charts/{chart['id']}", json={"spec": {**bar(mine), "type": "line"}})
    assert as_line.json()["spec"]["type"] == "line"

    copy = await client.post(f"/api/charts/{chart['id']}/duplicate")
    assert (copy.status_code, copy.json()["title"], copy.json()["spec"]["type"]) == (201, "Dev F1 (copy)", "line")

    resolved = await client.post("/api/charts/resolve", json={"spec": bar(mine)})
    assert resolved.status_code == 200
    [dataset] = resolved.json()["datasets"]
    assert (dataset["name"], dataset["kind"], dataset["region"]) == ("My runs", "user", None)
    assert resolved.json()["missing"] == []
    f1 = mine["columns"][1]["id"]
    assert dataset["rows"][0]["cells"][f1] == {"raw": "92.0", "value": 92.0, "error": None, "origin": "human",
                                               "original_raw": None, "page": None, "bbox": None}  # fmt: skip

    assert (await client.delete(f"/api/charts/{chart['id']}")).status_code == 204
    assert (await client.get(f"/api/charts/{chart['id']}")).status_code == 404


async def test_resolve_reports_missing_data_instead_of_failing(client):
    mine = await own_data(client)
    spec = bar(mine)
    spec["series"][0]["y"] = str(uuid.uuid4())

    resolved = await client.post("/api/charts/resolve", json={"spec": spec})

    assert resolved.status_code == 200
    assert resolved.json()["missing"] == [{"kind": "column", "id": spec["series"][0]["y"]}]


async def test_chart_errors_map_to_status_codes(client):
    mine = await own_data(client)
    unknown = uuid.uuid4()
    missing_column = bar(mine)
    missing_column["series"][0]["y"] = str(unknown)

    pie = {**bar(mine), "type": "pie"}
    assert (await client.post("/api/charts", json={"title": "F1", "spec": pie})).status_code == 422
    assert (await client.post("/api/charts", json={"title": "F1", "spec": missing_column})).status_code == 422
    assert (await client.post("/api/charts", json={"title": " ", "spec": bar(mine)})).status_code == 422
    assert (await client.post("/api/charts/resolve", json={"spec": {"type": "bar", "series": []}})).status_code == 422
    chart = (await client.post("/api/charts", json={"title": "F1", "spec": bar(mine)})).json()
    assert (await client.patch(f"/api/charts/{chart['id']}", json={})).status_code == 422
    assert (await client.patch(f"/api/charts/{chart['id']}", json={"spec": missing_column})).status_code == 422
    for method, path, json in [
        ("GET", f"/api/charts/{unknown}", None),
        ("PATCH", f"/api/charts/{unknown}", {"title": "x"}),
        ("DELETE", f"/api/charts/{unknown}", None),
        ("POST", f"/api/charts/{unknown}/duplicate", None),
        ("POST", f"/api/charts/{unknown}/note", None),
    ]:
        assert (await client.request(method, path, json=json)).status_code == 404


async def test_charts_in_notes_over_http(client, session):
    paper = await make_paper(session)
    table, mine = await captured_table(client, paper), await own_data(client)
    chart = (await client.post("/api/charts", json={"title": "SQuAD F1", "spec": bar(table, mine)})).json()

    made = await client.post(f"/api/charts/{chart['id']}/note")
    assert made.status_code == 201
    note = made.json()
    assert (note["body"], note["provenance"]) == ("", "human")
    assert note["charts"] == [{"id": chart["id"], "title": "SQuAD F1"}]
    assert note["anchors"] == [{"paper_id": str(paper.id), "page": 7, "bbox": [REGION], "quoted_text": "Table 2"}]
    assert [n["id"] for n in (await client.get(f"/api/papers/{paper.id}/notes")).json()] == [note["id"]]

    other = (await client.post("/api/charts", json={"title": "Mine", "spec": bar(mine)})).json()
    assert (await client.put(f"/api/notes/{note['id']}/charts/{other['id']}")).status_code == 204
    assert (await client.put(f"/api/notes/{note['id']}/charts/{other['id']}")).status_code == 204
    [listed] = (await client.get(f"/api/papers/{paper.id}/notes")).json()
    assert [c["title"] for c in listed["charts"]] == ["Mine", "SQuAD F1"]
    assert (await client.get(f"/api/charts/{other['id']}")).json()["note_ids"] == [note["id"]]

    assert (await client.delete(f"/api/notes/{note['id']}/charts/{other['id']}")).status_code == 204
    assert (await client.delete(f"/api/charts/{chart['id']}")).status_code == 204
    [kept] = (await client.get(f"/api/papers/{paper.id}/notes")).json()
    assert (kept["id"], kept["charts"]) == (note["id"], [])

    only_mine = await client.post(f"/api/charts/{other['id']}/note")
    assert (only_mine.status_code, only_mine.json()) == (422, {"detail": "chart_has_no_paper_data"})
    assert (await client.put(f"/api/notes/{uuid.uuid4()}/charts/{other['id']}")).status_code == 404
    assert (await client.put(f"/api/notes/{note['id']}/charts/{uuid.uuid4()}")).status_code == 404
    assert (await client.delete(f"/api/notes/{uuid.uuid4()}/charts/{other['id']}")).status_code == 404
