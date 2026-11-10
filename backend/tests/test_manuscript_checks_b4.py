import pytest

from app.core import manuscripts
from app.core.manuscript_checks import service
from app.core.manuscript_checks.registry import REGISTRY

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


def test_numbers_check_is_registered_cheap_and_after_pdf():
    names = [c.name for c in REGISTRY]
    assert next(c for c in REGISTRY if c.name == "numbers.unbacked").cost == "cheap"
    assert names.index("numbers.unbacked") > max(i for i, n in enumerate(names) if n.startswith("pdf."))


async def test_a_real_run_flags_an_unbacked_number_and_reads_json(session):
    from test_manuscript_papers import setup

    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Intro.\nOurs reaches 91.4 and 0.85 here.\n")
    await manuscripts.upsert_text(session, m.id, "results.json", '{"acc": 0.85}')
    run = await service.run_checks(session, m.id, cost="cheap")
    hits = [f for f in run.findings if f.check == "numbers.unbacked"]
    assert "numbers.unbacked" in run.ran
    assert [(f.file, f.line, f.message.split('"')[1]) for f in hits] == [("main.tex", 2, "91.4")]
