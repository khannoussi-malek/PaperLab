import pytest
from sqlalchemy.exc import IntegrityError

from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio


async def test_new_workspace_screening_defaults(session):
    workspace, _ = await make_pool(session, [])
    await session.refresh(workspace)
    assert (workspace.screening_criteria, workspace.screening_ranked_used) == (None, False)
    assert (workspace.suggest_status, workspace.suggest_done, workspace.suggest_total) == ("idle", 0, 0)


async def test_hit_suggestion_columns_round_trip(session):
    _, [hit] = await make_pool(session, [("sleep", None)])
    hit.suggestion, hit.suggestion_reason, hit.suggestion_note = "exclude", "wrong_study_type", "A review."
    await session.flush()
    await session.refresh(hit)
    assert (hit.suggestion, hit.suggestion_reason) == ("exclude", "wrong_study_type")


@pytest.mark.parametrize(("column", "value"), [("suggestion", "maybe"), ("suggestion_reason", "boring")])
async def test_hit_suggestion_checks_reject_unknown_values(session, column, value):
    _, [hit] = await make_pool(session, [("sleep", None)])
    setattr(hit, column, value)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_workspace_suggest_status_check(session):
    workspace, _ = await make_pool(session, [])
    workspace.suggest_status = "paused"
    with pytest.raises(IntegrityError):
        await session.flush()
