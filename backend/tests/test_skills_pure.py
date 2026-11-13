"""Bundled skill files, their loader, the merge with the reader's rows, and prompt composition (no database)."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core import skills
from app.core.prompts import PROMPTS_DIR
from app.core.skills import BundledSkill, SkillRow, compose, load_bundled, merge

BASE = "You are PaperLab. Cite [C1] for every claim."
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bundled(
    slug="check-evaluation", scope="both", version=1, instructions="Check the numbers.", label="Check it", lens="full"
):
    return BundledSkill(
        slug=slug,
        label=label,
        description=f"{slug} description",
        scope=scope,
        version=version,
        instructions=instructions,
        lens=lens,
    )


def row(builtin_slug=None, created=0, **fields):
    defaults = dict(
        id=uuid.uuid4(),
        builtin_slug=builtin_slug,
        label=None,
        description=None,
        scope=None,
        instructions=None,
        version=1,
        is_listed=True,
        is_paper_default=False,
        is_workspace_default=False,
        created_at=datetime(2026, 1, 1 + created, tzinfo=timezone.utc),
        lens=None,
    )
    return SkillRow(**{**defaults, **fields})


def write_skill(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)


GOOD = (
    "---\nslug: alpha\nlabel: Alpha\ndescription: A skill\nscope: paper\nversion: 1\nlens: full\n---\n"
    "Do the alpha task.\n"
)


# Loader


def test_the_six_bundled_files_load_in_the_fixed_order():
    loaded = load_bundled()
    assert [skill.slug for skill in loaded] == list(skills.ORDER)
    assert len(loaded) == 6
    assert skills.BUNDLED == loaded
    assert all(skill.instructions.strip() == skill.instructions for skill in loaded)


def test_other_files_load_after_the_fixed_order_by_slug(tmp_path):
    write_skill(tmp_path, "zeta.v2.md", GOOD.replace("alpha", "zeta").replace("version: 1", "version: 2"))
    write_skill(tmp_path, "alpha.v2.md", GOOD.replace("version: 1", "version: 2"))
    write_skill(tmp_path, "study-type.v2.md", GOOD.replace("alpha", "study-type").replace("version: 1", "version: 2"))
    assert [skill.slug for skill in load_bundled(tmp_path)] == ["study-type", "alpha", "zeta"]


def test_a_valid_file_becomes_a_frozen_bundled_skill(tmp_path):
    write_skill(tmp_path, "alpha.v1.md", GOOD)
    (skill,) = load_bundled(tmp_path)
    assert skill == BundledSkill(
        slug="alpha",
        label="Alpha",
        description="A skill",
        scope="paper",
        version=1,
        instructions="Do the alpha task.",
        lens="full",
    )


def test_a_duplicate_slug_raises(tmp_path):
    write_skill(tmp_path, "alpha.v1.md", GOOD)
    write_skill(tmp_path, "alpha.v2.md", GOOD.replace("version: 1", "version: 2"))
    with pytest.raises(ValueError, match="alpha"):
        load_bundled(tmp_path)


def test_a_name_that_disagrees_with_the_frontmatter_raises(tmp_path):
    write_skill(tmp_path, "beta.v1.md", GOOD)
    with pytest.raises(ValueError, match="beta"):
        load_bundled(tmp_path)


def test_a_version_in_the_name_that_disagrees_with_the_frontmatter_raises(tmp_path):
    write_skill(tmp_path, "alpha.v2.md", GOOD)
    with pytest.raises(ValueError, match="alpha"):
        load_bundled(tmp_path)


@pytest.mark.parametrize("field", ["slug", "label", "description", "scope", "version", "lens"])
def test_a_missing_frontmatter_field_raises(tmp_path, field):
    lines = [line for line in GOOD.splitlines() if not line.startswith(f"{field}:")]
    write_skill(tmp_path, "alpha.v1.md", "\n".join(lines) + "\n")
    with pytest.raises(ValueError, match=field):
        load_bundled(tmp_path)


def test_a_bad_scope_raises(tmp_path):
    write_skill(tmp_path, "alpha.v1.md", GOOD.replace("scope: paper", "scope: library"))
    with pytest.raises(ValueError, match="scope"):
        load_bundled(tmp_path)


def test_a_lens_that_is_not_a_lens_id_raises(tmp_path):
    write_skill(tmp_path, "alpha.v1.md", GOOD.replace("lens: full", "lens: everything"))
    with pytest.raises(ValueError, match="lens"):
        load_bundled(tmp_path)


def test_an_empty_body_raises(tmp_path):
    write_skill(
        tmp_path,
        "alpha.v1.md",
        "---\nslug: alpha\nlabel: Alpha\ndescription: A skill\nscope: paper\nversion: 1\n---\n  \n",
    )
    with pytest.raises(ValueError, match="alpha"):
        load_bundled(tmp_path)


def test_a_file_without_frontmatter_raises(tmp_path):
    write_skill(tmp_path, "alpha.v1.md", "Just a body.\n")
    with pytest.raises(ValueError, match="alpha.v1.md"):
        load_bundled(tmp_path)


# Merge


def test_a_bundled_skill_without_a_row_is_builtin_with_the_file_values():
    (view,) = merge([bundled()], [])
    assert (view.id, view.label, view.scope, view.instructions, view.version) == (
        "builtin:check-evaluation",
        "Check it",
        "both",
        "Check the numbers.",
        1,
    )
    assert (view.is_listed, view.is_paper_default, view.is_workspace_default, view.state) == (
        True,
        False,
        False,
        "builtin",
    )


def test_a_row_overrides_only_the_fields_it_sets():
    rows = [
        row(
            "check-evaluation",
            label="My check",
            instructions="Mine.",
            version=3,
            is_listed=False,
            is_paper_default=True,
        )
    ]
    (view,) = merge([bundled()], rows)
    assert (view.label, view.description, view.scope, view.instructions) == (
        "My check",
        "check-evaluation description",
        "both",
        "Mine.",
    )
    assert (view.version, view.is_listed, view.is_paper_default, view.state) == (3, False, True, "edited")


def test_a_bundled_skill_without_a_row_keeps_its_shipped_lens():
    (view,) = merge([bundled(lens="critical")], [])
    assert view.lens == "critical"


def test_a_row_lens_overrides_the_shipped_lens_and_keeps_the_text():
    (view,) = merge([bundled(lens="critical", instructions="Shipped.")], [row("check-evaluation", lens="method")])
    assert (view.lens, view.instructions, view.version, view.state) == ("method", "Shipped.", 1, "edited")


def test_a_row_without_a_lens_keeps_the_shipped_lens():
    (view,) = merge([bundled(lens="critical")], [row("check-evaluation", label="Renamed")])
    assert view.lens == "critical"


def test_a_custom_skill_is_full_unless_its_row_names_a_lens():
    (plain,) = merge([], [row(None, label="Plain", scope="paper", instructions="x", lens="full")])
    (lensed,) = merge([], [row(None, label="Lensed", scope="paper", instructions="x", lens="related")])
    assert (plain.lens, lensed.lens) == ("full", "related")


def test_a_label_only_row_stays_builtin_and_keeps_the_file_version():
    (view,) = merge([bundled(version=2)], [row("check-evaluation", label="Renamed", version=5)])
    assert (view.label, view.state, view.version) == ("Renamed", "builtin", 2)


def test_scope_and_description_overrides_apply():
    (view,) = merge([bundled()], [row("check-evaluation", scope="paper", description="New words")])
    assert (view.scope, view.description) == ("paper", "New words")


def test_a_row_for_a_removed_bundled_skill_is_ignored_and_logged_once(caplog):
    gone = row("removed-in-a-release-xyz", label="Old", instructions="Old text.")
    with caplog.at_level(logging.WARNING, logger="app.core.skills"):
        first = merge([bundled()], [gone])
        merge([bundled()], [gone])
    assert [view.id for view in first] == ["builtin:check-evaluation"]
    warnings = [r for r in caplog.records if "removed-in-a-release-xyz" in r.getMessage()]
    assert len(warnings) == 1


def test_a_custom_row_is_custom_with_its_own_id_and_version():
    custom_id = uuid.uuid4()
    (view,) = merge(
        [], [row(None, id=custom_id, label="Mine", description="d", scope="workspace", instructions="x", version=4)]
    )
    assert (view.id, view.state, view.version, view.scope) == (f"custom:{custom_id}", "custom", 4, "workspace")


def test_custom_rows_come_after_bundled_newest_first():
    older = row(None, created=0, label="Older", scope="paper", instructions="a")
    newer = row(None, created=5, label="Newer", scope="paper", instructions="b")
    views = merge([bundled()], [older, newer])
    assert [view.label for view in views] == ["Check it", "Newer", "Older"]


def test_kind_filter_keeps_the_kind_and_both():
    paper_only = bundled(slug="study-type", scope="paper", label="Study")
    both = bundled(slug="check-evaluation", scope="both", label="Check")
    workspace_only = bundled(slug="llm-reporting-ws", scope="workspace", label="Ws")
    kept = merge([paper_only, both, workspace_only], [], kind="paper")
    assert [view.label for view in kept] == ["Study", "Check"]
    assert [view.label for view in merge([paper_only, both, workspace_only], [], kind="workspace")] == ["Check", "Ws"]


def test_hidden_skills_are_dropped_only_when_asked():
    hidden = [row("check-evaluation", is_listed=False)]
    assert len(merge([bundled()], hidden)) == 1
    assert merge([bundled()], hidden, include_hidden=False) == []


def test_a_row_that_sets_no_instructions_keeps_the_file_text():
    (view,) = merge([bundled(instructions="Shipped.")], [row("check-evaluation", label="Renamed")])
    assert view.instructions == "Shipped."


# Compose


def test_no_skill_returns_the_base_prompt_byte_for_byte():
    assert compose(BASE, None) == BASE


def test_a_skill_is_appended_under_the_fixed_heading():
    (view,) = merge([bundled(instructions="Check the numbers.")], [])
    assert compose(BASE, view) == f"{BASE}\n\nYour task for this question:\nCheck the numbers."


def test_the_real_base_prompt_is_unchanged_when_no_skill_is_chosen():
    prompt = (PROMPTS_DIR / "chat.v7.md").read_text()
    assert compose(prompt, None) == prompt
