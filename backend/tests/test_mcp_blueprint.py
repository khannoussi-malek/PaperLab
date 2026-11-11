"""The create_manuscript_blueprint MCP tool: a starter blueprint.json, never an overwrite, logged as an AI step."""

import json

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call
from sqlalchemy import select

from app.core import manuscript_agent, manuscript_templates, manuscripts
from app.models import ManuscriptSnapshot

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


def starter(title, template):
    spec = manuscript_templates.get(template)
    targets = {} if spec is None else {s.id: list(s.words) for s in spec.sections}
    return json.dumps({"title": title, "contributions": [], "notation": [], "target_words": targets},
                      indent=2, ensure_ascii=False) + "\n"


async def test_the_starter_has_the_templates_bands(session):
    made = await manuscript_agent.create_manuscript(session, "Draft", "ieee")

    response = await call("create_manuscript_blueprint", manuscript_id=str(made.id))

    assert not response.is_error, response.content
    text = await manuscripts.get_text(session, made.id, "blueprint.json")
    assert text == starter("Draft", "ieee")
    assert text.endswith("}\n") and '\n  "contributions": [],' in text
    assert json.loads(text)["target_words"]["introduction"] == [400, 900]


async def test_a_custom_manuscript_gets_empty_targets(session):
    made = await manuscripts.create_from_files(session, title="Own layout", workspace_id=None,
                                               files={"main.tex": "x"}, main_file="main.tex")

    response = await call("create_manuscript_blueprint", manuscript_id=str(made.id))

    assert not response.is_error, response.content
    assert json.loads(await manuscripts.get_text(session, made.id, "blueprint.json")) == {
        "title": "Own layout", "contributions": [], "notation": [], "target_words": {}}


async def test_a_second_call_is_refused_and_the_file_is_unchanged(session):
    made = await manuscript_agent.create_manuscript(session, "Draft", "acm")
    await call("create_manuscript_blueprint", manuscript_id=str(made.id))
    before = await manuscripts.get_text(session, made.id, "blueprint.json")

    response = await call("create_manuscript_blueprint", manuscript_id=str(made.id))

    assert response.is_error and response.structured_content["error"] == "blueprint_exists"
    assert await manuscripts.get_text(session, made.id, "blueprint.json") == before


async def test_the_history_snapshot_carries_the_tool_and_reason(session):
    made = await manuscript_agent.create_manuscript(session, "Draft", "lncs")

    response = await call("create_manuscript_blueprint", manuscript_id=str(made.id), reason="plan the paper")

    assert not response.is_error, response.content
    [snap] = await session.scalars(
        select(ManuscriptSnapshot).where(ManuscriptSnapshot.manuscript_id == made.id,
                                         ManuscriptSnapshot.ai_tool == "create_manuscript_blueprint"))
    assert (snap.ai_path, snap.ai_reason) == ("blueprint.json", "plan the paper")
    assert response.structured_content["snapshot_id"] == str(snap.id)
