import io
import zipfile

import pytest

from app.core import manuscripts
from app.core.manuscript_checks import service
from app.core.manuscript_checks.registry import REGISTRY

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


def test_blueprint_checks_are_registered_cheap_and_last():
    names = [c.name for c in REGISTRY]
    assert names[-2:] == ["blueprint.words", "blueprint.notation"]
    assert {c.cost for c in REGISTRY if c.name.startswith("blueprint.")} == {"cheap"}


async def test_a_real_run_reads_blueprint_json_and_flags_an_off_target_section(session):
    from test_manuscript_papers import setup

    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "main.tex", "\\section{Method}\nOnly a few words.\n")
    await manuscripts.upsert_text(session, m.id, "blueprint.json", '{"target_words": {"method": [50, 100]}}')
    run = await service.run_checks(session, m.id, cost="cheap")
    hits = [f for f in run.findings if f.check == "blueprint.words"]
    # setup() builds from a template, so its skeleton section files are short too: they fall back to the
    # template's bands. main.tex's Method section uses the blueprint's own target.
    main = [f for f in hits if f.file == "main.tex"]
    assert [(f.file, f.line) for f in main] == [("main.tex", 1)]
    assert "the target is 50 to 100" in main[0].message
    assert any(f.file == "sections/results.tex" and "500 to 1500" in f.message for f in hits)


async def test_export_zip_keeps_blueprint_json(client):
    made = await client.post("/api/manuscripts", json={"title": "Draft", "template": "article"})
    mid = made.json()["id"]
    saved = await client.put(
        f"/api/manuscripts/{mid}/files/blueprint.json", json={"text": '{"title": "T"}', "base_updated_at": None}
    )
    assert saved.status_code == 200
    r = await client.get(f"/api/manuscripts/{mid}/export.zip", params={"pdf": "false"})
    assert "blueprint.json" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
