import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_manuscript_papers import setup

from app.core import manuscripts
from app.models import ManuscriptDraftReview as Row

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


def row(mid, **kw):
    return Row(manuscript_id=mid, status="queued", source="s", inputs={"files": []}, calls_max=11, **kw)


async def test_row_defaults_and_json_columns(session):
    _, _, m = await setup(session, "Alpha")
    session.add(row(m.id))
    await session.flush()
    got = await session.scalar(select(Row).where(Row.manuscript_id == m.id).execution_options(populate_existing=True))
    assert (got.mode, got.calls_done, got.confirm_remote, got.issues, got.refuted) == ("light", 0, False, None, None)


async def test_status_is_checked(session):
    _, _, m = await setup(session, "Alpha")
    session.add(Row(manuscript_id=m.id, status="paused", source="s", inputs={}, calls_max=11))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_mode_is_checked(session):
    _, _, m = await setup(session, "Alpha")
    session.add(Row(manuscript_id=m.id, mode="heavy", status="queued", source="s", inputs={}, calls_max=11))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_the_manuscript_deletes_its_review(session):
    _, _, m = await setup(session, "Alpha")
    session.add(row(m.id))
    await session.flush()
    await manuscripts.delete(session, m.id)
    gone = select(Row).where(Row.manuscript_id == m.id).execution_options(populate_existing=True)
    assert await session.scalar(gone) is None
