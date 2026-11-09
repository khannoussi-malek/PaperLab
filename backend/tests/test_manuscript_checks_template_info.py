import pytest

from app.core import manuscripts
from app.core.manuscript_checks import service
from app.core.manuscript_checks.base import ManuscriptInfo

pytestmark = pytest.mark.anyio


def test_default_is_custom():
    info = ManuscriptInfo("x", "main.tex", "never", None, None, None)
    assert info.template == "custom"


async def test_load_context_carries_the_template(session):
    m = await manuscripts.create(session, title="T", template="acm", workspace_id=None)
    ctx = await service.load_context(session, m.id)
    assert ctx.manuscript.template == "acm"
    imp = await manuscripts.create_from_files(session, title="I", workspace_id=None,
                                              files={"main.tex": "x"}, main_file="main.tex")
    assert (await service.load_context(session, imp.id)).manuscript.template == "custom"
