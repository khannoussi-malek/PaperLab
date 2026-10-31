import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
from test_manuscript_papers import setup
from test_manuscript_section_review_api import names

from app.core import diagram_compile, queue
from app.workers import manuscript_diagrams as worker
from app.workers import manuscripts as compile_worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
ALLOWED = set(
    "id description status code libraries compiled errors line message labels_not_in_description reason model ai "
    "created_at updated_at".split()
)
BANNED = {"text", "insert", "latex", "suggestion", "replacement", "rewrite", "wording"}
PIC = "\\begin{tikzpicture}\n\\node (a) {Encoder};\n\\node[right=of a] {Decoder};\n\\end{tikzpicture}"


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    async def stream(self, system, prompt):
        yield f"<tikz>\n\\usetikzlibrary{{positioning}}\n{PIC}\n</tikz>"


async def compiles(libraries, picture):
    return diagram_compile.PreviewResult(True, b"%PDF-fake", [], None)


@pytest.fixture(autouse=True)
def wiring(session, arq, monkeypatch, local_default_model, pdf_dir):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    monkeypatch.setattr(compile_worker, "COMPILE_LOCK", asyncio.Lock())


def diagram_properties(spec: dict) -> set[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(spec["components"]["schemas"][node["$ref"].rsplit("/", 1)[1]])
            found.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path, methods in spec["paths"].items():
        if "/diagrams" in path:
            for op in methods.values():
                for code, response in op["responses"].items():
                    if code.startswith("2"):
                        walk(response.get("content", {}))
    return found


async def test_the_routes_carry_code_only_in_diagram_out_and_never_prose(client, session, app):
    spec = app.openapi()
    allowlist = diagram_properties(spec)
    assert allowlist == ALLOWED, allowlist ^ ALLOWED
    assert not allowlist & BANNED
    holders = {n for n, s in spec["components"]["schemas"].items() if "code" in s.get("properties", {})}
    assert holders == {"DiagramOut", "DiagramCodeIn"}

    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    base = f"/api/manuscripts/{m.id}/diagrams"
    created = await client.post(base, json={"description": "An encoder feeds a decoder."})
    assert created.status_code == 202, created.text
    did = created.json()["id"]
    assert (await client.get(f"{base}/{did}/pdf")).status_code == 404
    await worker.generate_manuscript_diagram({"llm": Scripted(), "compile": compiles}, did)
    got = (await client.get(f"{base}/{did}")).json()
    pdf = await client.get(f"{base}/{did}/pdf")
    edited = await client.put(f"{base}/{did}/code", json={"code": PIC})
    cancelled = (await client.post(f"{base}/{did}/cancel")).json()
    for body in (created.json(), got, edited.json(), cancelled):
        assert names(body) <= ALLOWED and not names(body) & BANNED
    assert (got["status"], got["compiled"], got["code"], got["ai"]) == ("done", True, PIC, True)
    assert (pdf.status_code, pdf.headers["content-type"], pdf.content) == (200, "application/pdf", b"%PDF-fake")
    assert pdf.headers["cache-control"] == "no-store"
    assert (edited.status_code, edited.json()["status"]) == (202, "queued")
    assert (cancelled["status"], cancelled["reason"]) == ("failed", "cancelled")
    assert (await client.delete(f"{base}/{did}")).status_code == 204
    assert (await client.get(f"{base}/{did}")).status_code == 404


async def test_error_codes(client, session):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    base = f"/api/manuscripts/{m.id}/diagrams"
    bad = await client.post(base, json={"description": " "})
    assert (bad.status_code, bad.json()["detail"]) == (422, "description_invalid")
    assert (await client.post(base, json={"description": "x", "extra": 1})).status_code == 422
    assert (
        await client.post(f"/api/manuscripts/{uuid.uuid4()}/diagrams", json={"description": "x"})
    ).status_code == 404
    unknown = await client.get(f"{base}/{uuid.uuid4()}")
    assert (unknown.status_code, unknown.json()["detail"]) == (404, "unknown_diagram")
    assert (await client.post(base, json={"description": "An encoder."})).status_code == 202
    running = await client.post(base, json={"description": "An encoder."})
    assert (running.status_code, running.json()["detail"]) == (409, "diagram_running")
