import pytest

from app.core import manuscripts
from app.core.manuscript_checks import service
from app.core.manuscript_checks.registry import REGISTRY, select

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
NAMES = [
    "citations.missing_keys",
    "wording.ai_phrase", "wording.overclaim",
    "latex.markdown_leak", "latex.placeholder", "latex.numbered_heading", "latex.stray_preamble",
    "latex.non_ascii", "latex.notation_undefined", "latex.adjacent_cites", "latex.table_width",
    "references.duplicate_key", "references.stub_entry", "references.unused_entry", "references.zero_cite_section",
]


def test_registry_holds_the_fifteen_checks_all_cheap_and_no_doi_check():
    assert [c.name for c in REGISTRY] == NAMES
    assert all(c.cost == "cheap" for c in REGISTRY)
    assert [c.name for c in select(cost="cheap")] == NAMES


async def test_a_real_run_gives_a_finding_from_each_family(session):
    from test_manuscript_papers import setup
    _, _, m = await setup(session, "Deep learning")
    words = " ".join(["word"] * 45)
    await manuscripts.upsert_text(session, m.id, "main.tex",
        f"\\section{{Introduction}}\n{words} It is worth noting this is robust. TODO\n## Heading\n")
    await manuscripts.upsert_text(session, m.id, "refs.bib", "@misc{k, title={Only a title}}\n")
    run = await service.run_checks(session, m.id)
    seen = {f.check for f in run.findings}
    assert {"wording.ai_phrase", "wording.overclaim", "latex.placeholder", "latex.markdown_leak",
            "references.zero_cite_section", "references.stub_entry", "references.unused_entry"} <= seen
    assert "references.doi_resolves" not in run.ran


async def test_clean_text_makes_no_check_crash(session):
    # F0's registry test covers crash isolation; this pins that no B2 check crashes on plain text.
    from test_manuscript_papers import setup
    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Plain text.\n")
    run = await service.run_checks(session, m.id)
    assert not [f for f in run.findings if f.message.startswith("This check crashed")]
