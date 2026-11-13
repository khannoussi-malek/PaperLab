"""The skills table and its service (M17 spec §3, §4, §8). Real Postgres; every test rolls back."""

import uuid

import pytest
from sqlalchemy import func, select, text

from app.core import skills
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Skill

pytestmark = pytest.mark.anyio

LONG_TEXT = "Check it carefully. " * 200  # about 4000 characters: inside the 8000 limit


async def make_custom(session, label="My check", scope="paper", instructions="Do the check.", description="d"):
    return await skills.create(session, label=label, description=description, scope=scope, instructions=instructions)


async def view(session, skill_id):
    return await skills.get_view(session, skill_id)


async def row_for(session, builtin_slug):
    return (await session.execute(select(Skill).where(Skill.builtin_slug == builtin_slug))).scalar_one_or_none()


# list_skills


async def test_the_six_bundled_skills_are_listed_as_builtin(session):
    listed = await skills.list_skills(session)
    assert [v.id for v in listed] == [f"builtin:{slug}" for slug in skills.ORDER]
    assert {v.state for v in listed} == {"builtin"}
    assert not any(v.is_paper_default or v.is_workspace_default for v in listed)


async def test_hidden_skills_leave_the_picker_list_but_stay_in_settings(session):
    await skills.update(session, "builtin:study-type", is_listed=False)
    picker = await skills.list_skills(session, kind="paper")
    settings = await skills.list_skills(session, kind="paper", include_hidden=True)
    assert "builtin:study-type" not in [v.id for v in picker]
    assert "builtin:study-type" in [v.id for v in settings]


async def test_the_kind_filter_offers_only_what_fits_the_chat(session):
    paper_ids = {v.id for v in await skills.list_skills(session, kind="paper", include_hidden=True)}
    workspace_ids = {v.id for v in await skills.list_skills(session, kind="workspace", include_hidden=True)}
    assert "builtin:study-type" in paper_ids and "builtin:study-type" not in workspace_ids
    assert "builtin:check-evaluation" in paper_ids and "builtin:check-evaluation" in workspace_ids


# create


async def test_create_makes_a_custom_skill_at_version_one(session):
    created = await make_custom(session, label="  My check  ", instructions="  Do it.  ")
    assert created.id.startswith("custom:")
    assert (created.label, created.instructions, created.version, created.state) == ("My check", "Do it.", 1, "custom")
    assert created.is_listed and not created.is_paper_default


async def test_custom_skills_are_listed_after_the_bundled_ones_newest_first(session):
    await make_custom(session, label="First one")
    await make_custom(session, label="Second one")
    listed = await skills.list_skills(session, include_hidden=True)
    assert [v.label for v in listed[6:]] == ["Second one", "First one"]


@pytest.mark.parametrize("label", ["check the evaluation", "CHECK THE EVALUATION"])
async def test_a_label_is_refused_when_another_skill_has_it_ignoring_case(session, label):
    with pytest.raises(Conflict) as error:
        await make_custom(session, label=label)
    assert error.value.args[0] == "skill_label_taken"


async def test_a_label_already_taken_by_a_custom_skill_is_refused(session):
    await make_custom(session, label="Mine")
    with pytest.raises(Conflict, match="skill_label_taken"):
        await make_custom(session, label="mine")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"label": "   "},
        {"label": "x" * 81},
        {"description": "x" * 201},
        {"scope": "library"},
        {"instructions": "   "},
        {"instructions": "x" * 8001},
    ],
)
async def test_field_limits_are_invalid_input(session, kwargs):
    with pytest.raises(InvalidInput):
        await make_custom(session, **{"label": "Ok", **kwargs})


async def test_a_label_of_eighty_characters_is_allowed(session):
    created = await make_custom(session, label="x" * 80)
    assert len(created.label) == 80


# update


async def test_the_first_edit_of_a_bundled_skill_inserts_its_row_and_bumps_version(session):
    assert await row_for(session, "check-evaluation") is None
    edited = await skills.update(session, "builtin:check-evaluation", instructions="Mine.")
    assert await row_for(session, "check-evaluation") is not None
    assert (edited.instructions, edited.state, edited.version) == ("Mine.", "edited", 2)


async def test_a_second_instructions_change_bumps_version_again(session):
    await skills.update(session, "builtin:check-evaluation", instructions="One.")
    edited = await skills.update(session, "builtin:check-evaluation", instructions="Two.")
    assert edited.version == 3


async def test_saving_the_same_instructions_does_not_bump_version(session):
    shipped = (await view(session, "builtin:check-evaluation")).instructions
    unchanged = await skills.update(session, "builtin:check-evaluation", instructions=shipped)
    assert unchanged.version == 1


async def test_a_label_only_edit_keeps_the_shipped_text_and_version(session):
    renamed = await skills.update(session, "builtin:check-evaluation", label="Test the numbers")
    shipped = skills.BUNDLED[1]
    assert (renamed.label, renamed.state, renamed.version) == ("Test the numbers", "builtin", shipped.version)
    assert renamed.instructions == shipped.instructions


async def test_only_the_sent_fields_change(session):
    custom = await make_custom(session, label="Keep", description="old words", instructions="Kept.")
    updated = await skills.update(session, custom.id, description="new words")
    assert (updated.label, updated.description, updated.instructions) == ("Keep", "new words", "Kept.")


async def test_updating_a_custom_skill_bumps_version_on_instructions_only(session):
    custom = await make_custom(session, instructions="One.")
    relabelled = await skills.update(session, custom.id, label="Relabelled")
    assert relabelled.version == 1
    reworded = await skills.update(session, custom.id, instructions="Two.")
    assert reworded.version == 2


async def test_renaming_into_a_taken_label_is_refused_but_keeping_your_own_is_fine(session):
    await make_custom(session, label="Taken")
    mine = await make_custom(session, label="Mine")
    with pytest.raises(Conflict, match="skill_label_taken"):
        await skills.update(session, mine.id, label="taken")
    assert (await view(session, mine.id)).label == "Mine"
    assert (await skills.update(session, mine.id, label="Mine")).label == "Mine"


async def test_renaming_a_bundled_skill_into_a_custom_label_is_refused(session):
    await make_custom(session, label="Taken")
    with pytest.raises(Conflict, match="skill_label_taken"):
        await skills.update(session, "builtin:study-type", label="TAKEN")


async def test_hiding_a_skill_clears_both_of_its_defaults(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    hidden = await skills.update(session, "builtin:study-type", is_listed=False)
    assert (hidden.is_listed, hidden.is_paper_default, hidden.is_workspace_default) == (False, False, False)


async def test_narrowing_scope_clears_a_default_the_new_scope_no_longer_covers(session):
    await skills.set_default(session, "builtin:check-evaluation", "workspace", True)
    narrowed = await skills.update(session, "builtin:check-evaluation", scope="paper")
    assert narrowed.scope == "paper" and narrowed.is_workspace_default is False


async def test_an_update_of_an_unknown_skill_is_not_found(session):
    with pytest.raises(NotFound, match="skill_not_found"):
        await skills.update(session, "builtin:nope", label="x")


async def test_a_malformed_custom_id_is_not_found_not_a_crash(session):
    with pytest.raises(NotFound, match="skill_not_found"):
        await skills.get_view(session, "custom:not-a-uuid")


# delete


async def test_a_custom_skill_can_be_deleted_and_its_default_goes_with_it(session):
    custom = await make_custom(session)
    await skills.set_default(session, custom.id, "paper", True)
    await skills.delete(session, custom.id)
    assert custom.id not in [v.id for v in await skills.list_skills(session, include_hidden=True)]
    with pytest.raises(NotFound):
        await skills.get_view(session, custom.id)


async def test_a_bundled_skill_cannot_be_deleted(session):
    with pytest.raises(Conflict, match="builtin_skill"):
        await skills.delete(session, "builtin:study-type")


async def test_deleting_an_unknown_skill_is_not_found(session):
    with pytest.raises(NotFound, match="skill_not_found"):
        await skills.delete(session, f"custom:{uuid.uuid4()}")


# reset


async def test_reset_returns_the_shipped_text_and_keeps_hidden_and_default_state(session):
    await skills.update(session, "builtin:check-evaluation", label="Mine", instructions="Mine.")
    await skills.update(session, "builtin:check-evaluation", is_listed=False)
    await skills.set_default(session, "builtin:check-evaluation", "paper", True)
    before = await row_for(session, "check-evaluation")
    version_before = before.version

    reset = await skills.reset(session, "builtin:check-evaluation")

    shipped = skills.BUNDLED[1]
    assert (reset.label, reset.instructions, reset.state) == (shipped.label, shipped.instructions, "builtin")
    assert (reset.is_listed, reset.is_paper_default) == (False, True)
    assert reset.version == shipped.version
    assert (await row_for(session, "check-evaluation")).version == version_before + 1


async def test_reset_refuses_a_custom_skill(session):
    custom = await make_custom(session)
    with pytest.raises(Conflict, match="custom_skill"):
        await skills.reset(session, custom.id)


async def test_reset_of_an_untouched_bundled_skill_changes_nothing(session):
    untouched = await skills.reset(session, "builtin:study-type")
    assert untouched.state == "builtin"
    assert await row_for(session, "study-type") is None


# set_default


async def test_setting_a_paper_default_moves_it_from_the_old_holder(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    await skills.set_default(session, "builtin:check-evaluation", "paper", True)
    listed = {v.id: v for v in await skills.list_skills(session, kind="paper", include_hidden=True)}
    assert listed["builtin:check-evaluation"].is_paper_default
    assert not listed["builtin:study-type"].is_paper_default


async def test_two_sequential_default_moves_leave_one_holder_and_no_error(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    await skills.set_default(session, "builtin:plain-explanation", "paper", True)
    holders = (
        await session.execute(select(func.count()).select_from(Skill).where(Skill.is_paper_default))
    ).scalar_one()
    assert holders == 1


async def test_two_sequential_default_moves_per_kind_leave_one_holder_each(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    await skills.set_default(session, "builtin:plain-explanation", "paper", True)
    await skills.set_default(session, "builtin:check-evaluation", "workspace", True)
    await skills.set_default(session, "builtin:unstated-limits", "workspace", True)
    paper_holders = await session.scalar(select(func.count()).select_from(Skill).where(Skill.is_paper_default))
    workspace_holders = await session.scalar(select(func.count()).select_from(Skill).where(Skill.is_workspace_default))
    assert (paper_holders, workspace_holders) == (1, 1)


async def test_each_chat_kind_has_its_own_default(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    await skills.set_default(session, "builtin:check-evaluation", "workspace", True)
    shown = {v.id: v for v in await skills.list_skills(session, include_hidden=True)}
    assert shown["builtin:study-type"].is_paper_default and not shown["builtin:study-type"].is_workspace_default
    assert shown["builtin:check-evaluation"].is_workspace_default
    assert not shown["builtin:check-evaluation"].is_paper_default


async def test_a_workspace_default_on_a_paper_only_skill_is_a_scope_conflict(session):
    with pytest.raises(Conflict, match="skill_scope"):
        await skills.set_default(session, "builtin:study-type", "workspace", True)


async def test_switching_a_default_off_clears_it(session):
    await skills.set_default(session, "builtin:study-type", "paper", True)
    off = await skills.set_default(session, "builtin:study-type", "paper", False)
    assert off.is_paper_default is False


async def test_deleting_the_default_skill_leaves_no_default_behind(session):
    custom = await make_custom(session, scope="workspace")
    await skills.set_default(session, custom.id, "workspace", True)
    await skills.delete(session, custom.id)
    assert not [v for v in await skills.list_skills(session, kind="workspace") if v.is_workspace_default]


async def test_both_default_indexes_exist_as_partial_unique_indexes(session):
    rows = (
        await session.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'skills' AND indexdef LIKE '%UNIQUE%'")
        )
    ).all()
    definitions = {name: definition for name, definition in rows}
    assert "WHERE is_paper_default" in definitions["skills_one_paper_default"]
    assert "WHERE is_workspace_default" in definitions["skills_one_workspace_default"]


# resolve


async def test_resolve_with_no_skill_is_none(session):
    assert await skills.resolve(session, None, "paper") is None


async def test_resolve_of_an_unknown_id_is_not_found(session):
    with pytest.raises(NotFound, match="skill_not_found"):
        await skills.resolve(session, f"custom:{uuid.uuid4()}", "paper")


async def test_a_hidden_skill_still_resolves_for_an_explicit_request(session):
    await skills.update(session, "builtin:study-type", is_listed=False)
    resolved = await skills.resolve(session, "builtin:study-type", "paper")
    assert resolved.id == "builtin:study-type"


async def test_resolve_refuses_a_skill_outside_the_chat_scope(session):
    with pytest.raises(Conflict, match="skill_scope"):
        await skills.resolve(session, "builtin:study-type", "workspace")


async def test_resolve_accepts_both_scope_in_either_chat(session):
    assert (await skills.resolve(session, "builtin:check-evaluation", "workspace")).id == "builtin:check-evaluation"
    assert (await skills.resolve(session, "builtin:check-evaluation", "paper")).id == "builtin:check-evaluation"


# A bundled skill removed in a release


async def test_a_row_for_a_removed_bundled_skill_is_ignored_and_its_id_is_not_found(session):
    session.add(Skill(builtin_slug="removed-in-a-release", label="Old", instructions="Old.", scope="paper"))
    await session.flush()
    ids = [v.id for v in await skills.list_skills(session, include_hidden=True)]
    assert "builtin:removed-in-a-release" not in ids and len(ids) == 6
    with pytest.raises(NotFound, match="skill_not_found"):
        await skills.resolve(session, "builtin:removed-in-a-release", "paper")
