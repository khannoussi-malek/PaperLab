"""The bundled skills' instructions follow the spec's rules (M17 §5): the base chat prompt owns citations and the
answer's format, so no skill restates them, and a skill for several papers never says "this paper"."""

import re

import pytest

from app.core.skills import BUNDLED

FORMAT_WORDS = re.compile(r"\[C\d*|\bcit(e|es|ed|ing|ation|ations)\b|\bformat(ting|ted)?\b|\bmarkdown\b", re.I)


@pytest.mark.parametrize("skill", BUNDLED, ids=lambda s: s.slug)
def test_a_skill_never_restates_citation_or_format_rules(skill):
    assert FORMAT_WORDS.search(skill.instructions) is None


@pytest.mark.parametrize("skill", [s for s in BUNDLED if s.scope == "both"], ids=lambda s: s.slug)
def test_a_skill_for_several_papers_never_says_this_paper(skill):
    assert "this paper" not in skill.instructions.lower()


@pytest.mark.parametrize("skill", BUNDLED, ids=lambda s: s.slug)
def test_each_skill_is_a_real_task_not_a_one_liner_or_an_essay(skill):
    assert 400 <= len(skill.instructions) <= 2500


def test_six_skills_ship_and_four_credit_the_guidelines_they_draw_on():
    assert [s.slug for s in BUNDLED] == [
        "study-type",
        "check-evaluation",
        "check-validation",
        "unstated-limits",
        "llm-reporting",
        "plain-explanation",
    ]
    assert sum("llm-guidelines.org" in s.description for s in BUNDLED) == 4
