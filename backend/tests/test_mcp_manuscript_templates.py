"""The list_manuscript_templates MCP tool and the core summaries the API shares, through an in-process client."""

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call

from app.core import manuscript_templates

pytestmark = pytest.mark.anyio

FIELDS = {"name", "label", "official", "provenance", "page_limit", "references_count", "section_words"}
NAMES = ["article", "ieee", "acm", "lncs", "elsevier"]


async def test_summaries_are_plain_dicts_with_the_listed_fields():
    got = manuscript_templates.summaries()
    assert [t["name"] for t in got] == NAMES
    assert all(set(t) == FIELDS for t in got)
    ieee = next(t for t in got if t["name"] == "ieee")
    assert (ieee["label"], ieee["official"], ieee["page_limit"], ieee["references_count"]) == (
        "IEEE conference", True, 6, True)
    assert ieee["section_words"]["introduction"] == (400, 900)


async def test_the_tool_lists_all_five_templates_with_their_fields():
    response = await call("list_manuscript_templates")

    assert not response.is_error, response.content
    templates = response.structured_content["result"]
    assert [t["name"] for t in templates] == NAMES
    assert all(set(t) == FIELDS for t in templates)
    article = templates[0]
    assert (article["page_limit"], article["official"], article["references_count"]) == (None, False, False)
    assert article["section_words"]["introduction"] == [400, 900]
    assert set(article["section_words"]) == {"introduction", "related-work", "method", "results", "discussion",
                                             "conclusion"}
