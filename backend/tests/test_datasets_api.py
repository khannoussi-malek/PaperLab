import uuid

import pytest
from conftest import TABLE_ROWS
from sqlalchemy import insert

from app.models import Chart, Paper, chart_datasets

pytestmark = pytest.mark.anyio

TABLE_REGION = [60.0, 135.0, 420.0, 185.0]


def user_grid(*rows) -> dict:
    return {
        "columns": [{"name": "Model"}, {"name": "F1", "unit": "%"}],
        "rows": [{"cells": [{"raw": text} for text in row]} for row in rows],
    }


async def make_paper(session, path="/nonexistent.pdf", page_count=1) -> Paper:
    paper = Paper(title="Attention Is All You Need", file_path=str(path), page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


async def test_own_data_lifecycle_over_http(client):
    created = await client.post(
        "/api/datasets", json={"name": "My runs", "kind": "user", "grid": user_grid(("run 1", "92.0 ± 0.4"))}
    )
    assert created.status_code == 201
    dataset = created.json()
    assert (dataset["name"], dataset["kind"], dataset["paper_id"], dataset["row_count"]) == ("My runs", "user", None, 1)
    model, f1 = dataset["columns"]
    assert (f1["name"], f1["unit"], f1["position"]) == ("F1", "%", 1)
    cell = dataset["rows"][0]["cells"][1]
    assert cell == {"column_id": f1["id"], "raw": "92.0 ± 0.4", "value": 92.0, "error": 0.4, "origin": "human",
                    "original_raw": None, "page": None, "bbox": None}  # fmt: skip
    assert (await client.get(f"/api/datasets/{dataset['id']}")).json() == dataset
    assert dataset["id"] in [d["id"] for d in (await client.get("/api/datasets")).json()]

    renamed = await client.patch(f"/api/datasets/{dataset['id']}", json={"name": "Seeds"})
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Seeds")

    row_id = dataset["rows"][0]["id"]
    saved = await client.put(
        f"/api/datasets/{dataset['id']}/grid",
        json={"columns": [{"id": f1["id"], "name": "F1"}, {"id": model["id"], "name": "Model"}],
              "rows": [{"id": row_id, "cells": [{"raw": "93"}, {"raw": "run 1"}]}]},
    )  # fmt: skip
    assert saved.status_code == 200
    assert [c["id"] for c in saved.json()["columns"]] == [f1["id"], model["id"]]
    assert saved.json()["rows"][0]["id"] == row_id

    assert (await client.delete(f"/api/datasets/{dataset['id']}")).status_code == 204
    assert (await client.get(f"/api/datasets/{dataset['id']}")).status_code == 404


async def test_capture_a_table_and_a_number_over_http(client, session, table_pdf):
    paper = await make_paper(session, table_pdf)

    preview = await client.post(f"/api/papers/{paper.id}/tables/preview", json={"page": 1, "region": TABLE_REGION})
    assert preview.status_code == 200
    body = preview.json()
    assert body["name"] == "Table 1: Results on the dev set."
    assert [[c["raw"] for c in row["cells"]] for row in body["grid"]["rows"]] == [list(r) for r in TABLE_ROWS[1:]]
    assert body["grid"]["columns"] == [{"id": None, "name": name, "unit": None} for name in TABLE_ROWS[0]]

    created = await client.post(
        "/api/datasets",
        json={"name": body["name"], "kind": "table", "paper_id": str(paper.id), "page": 1, "region": TABLE_REGION,
              "grid": body["grid"]},
    )  # fmt: skip
    assert created.status_code == 201
    table = created.json()
    assert (table["region"], table["rows"][1]["cells"][1]["origin"]) == (TABLE_REGION, "extracted")

    candidates = await client.post("/api/numbers/candidates", json={"text": "reaches 90.9 ± 0.2 F1 on dev"})
    assert candidates.json() == [{"raw": "90.9 ± 0.2", "value": 90.9, "error": 0.2, "unit_hint": "F1"}]

    added = await client.post(
        f"/api/papers/{paper.id}/numbers",
        json={"label": "Dev F1", "raw": "90.9 ± 0.2", "unit": "F1", "page": 1, "bbox": [[220, 170, 270, 182]]},
    )
    assert added.status_code == 201
    listed = (await client.get("/api/datasets", params={"paper_id": str(paper.id)})).json()
    assert [(d["kind"], d["paper_title"]) for d in listed] == [("table", paper.title), ("numbers", paper.title)]
    assert added.json()["dataset_id"] == listed[1]["id"]


async def test_import_csv_over_http(client):
    named = await client.post(
        "/api/datasets/import",
        files={"file": ("runs.csv", b"Model,F1\nmine,92.0\n", "text/csv")},
        data={"name": "My runs"},
    )
    assert (named.status_code, named.json()["name"]) == (201, "My runs")
    assert named.json()["rows"][0]["cells"][1]["value"] == 92.0

    unnamed = await client.post("/api/datasets/import", files={"file": ("x.csv", b"Seed\n1\n", "text/csv")})
    assert (unnamed.status_code, unnamed.json()["name"]) == (201, "Imported data")

    broken = await client.post("/api/datasets/import", files={"file": ("x.csv", b"a,b\n1,2,3\n", "text/csv")})
    assert broken.json() == {"detail": "row 2 has 3 values, but the header has 2"}
    assert broken.status_code == 422


async def test_dataset_and_capture_errors_map_to_status_codes(client, session, table_pdf):
    paper = await make_paper(session, table_pdf)
    unknown = uuid.uuid4()
    grid = user_grid(("a", "1"))

    async def preview(paper_id, page=1, region=TABLE_REGION) -> int:
        body = {"page": page, "region": region}
        return (await client.post(f"/api/papers/{paper_id}/tables/preview", json=body)).status_code

    assert (await preview(unknown), await preview(paper.id, page=2), await preview(paper.id, region=[1, 2, 3])) == (
        404, 422, 422
    )
    assert (await client.post("/api/datasets", json={"name": "T", "kind": "table", "paper_id": str(paper.id), "page": 1,
                                                     "grid": grid})).status_code == 422
    assert (await client.post("/api/datasets", json={"name": "T", "kind": "numbers", "grid": grid})).status_code == 422
    assert (await client.post("/api/datasets", json={"name": " ", "kind": "user", "grid": grid})).status_code == 422
    assert (await client.post("/api/numbers/candidates", json={"text": "x" * 5001})).status_code == 422
    number = {"label": "F1", "raw": "high", "unit": "", "page": 1, "bbox": [[1, 2, 3, 4]]}
    assert (await client.post(f"/api/papers/{paper.id}/numbers", json=number)).status_code == 422
    assert (await client.post(f"/api/papers/{unknown}/numbers", json={**number, "raw": "1"})).status_code == 404
    no_rects = {**number, "raw": "1", "bbox": []}
    assert (await client.post(f"/api/papers/{paper.id}/numbers", json=no_rects)).status_code == 422

    for method, path, json in [
        ("GET", f"/api/datasets/{unknown}", None),
        ("PATCH", f"/api/datasets/{unknown}", {"name": "x"}),
        ("PUT", f"/api/datasets/{unknown}/grid", grid),
        ("DELETE", f"/api/datasets/{unknown}", None),
    ]:
        assert (await client.request(method, path, json=json)).status_code == 404
    assert (await client.get("/api/datasets", params={"paper_id": str(unknown)})).status_code == 404

    created = (await client.post("/api/datasets", json={"name": "Runs", "kind": "user", "grid": grid})).json()
    assert (await client.patch(f"/api/datasets/{created['id']}", json={"name": " "})).status_code == 422
    ragged = {"columns": [{"name": "a"}, {"name": "b"}], "rows": [{"cells": [{"raw": "1"}]}]}
    assert (await client.put(f"/api/datasets/{created['id']}/grid", json=ragged)).status_code == 422

    chart = Chart(title="Runs chart", spec={"version": 1, "y": created["columns"][1]["id"]}, spec_version=1)
    session.add(chart)
    await session.flush()
    await session.execute(insert(chart_datasets).values(chart_id=chart.id, dataset_id=created["id"]))
    await session.commit()
    refused = await client.delete(f"/api/datasets/{created['id']}")
    assert (refused.status_code, refused.json()) == (409, {"detail": "used_by_charts"})
    assert (await client.get(f"/api/datasets/{created['id']}")).json()["charts"] == [
        {"id": str(chart.id), "title": "Runs chart", "column_ids": [created["columns"][1]["id"]]}
    ]
    assert (await client.delete(f"/api/datasets/{created['id']}", params={"force": "true"})).status_code == 204
