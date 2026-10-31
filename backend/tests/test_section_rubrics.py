import pytest

from app.core.errors import InvalidInput
from app.core.section_rubrics import RUBRICS, rubric_for
from app.core.sections import ROLES

FORBIDDEN = ("rewrite", "reword", "replace", "suggest", "replacement", "instead of")


def test_every_reviewable_role_has_a_rubric():
    assert set(RUBRICS) == set(ROLES) - {"back", "other"}


def test_items_are_short_and_never_ask_for_rewrites():
    for role, items in RUBRICS.items():
        assert 3 <= len(items) <= 6, role
        assert len({i.id for i in items}) == len(items)
        for i in items:
            assert 0 < len(i.text) <= 120, i
            assert not any(w in i.text.lower() for w in FORBIDDEN), i


def test_rubric_for():
    assert rubric_for("intro") is RUBRICS["intro"]
    for bad in ("back", "other", "bogus"):
        with pytest.raises(InvalidInput) as e:
            rubric_for(bad)
        assert str(e.value) == "unknown_role"
        assert e.value.details == {"detail": "Pick what kind of section this is."}
