import pytest

from app.core import manuscript_history, manuscripts
from app.core import manuscript_section_ops as ops
from app.core.errors import Conflict, InvalidInput

pytestmark = pytest.mark.anyio


async def new(session):
    return await manuscripts.create(session, title="S", template="article", workspace_id=None)


async def main_of(session, mid) -> str:
    return (await manuscripts.read(session, mid, "main.tex")).text


def inputs(main: str) -> list[str]:
    return [ln for ln in main.splitlines() if ln.startswith("\\input{")]


async def test_add_writes_the_file_and_the_input_after_a_snapshot(session):
    m = await new(session)
    path = await ops.add(session, m.id, title="Threats to validity", after="sections/discussion.tex")
    assert path == "sections/threats-to-validity.tex"
    main = await main_of(session, m.id)
    assert (main.index("\\input{sections/discussion}") < main.index("\\input{sections/threats-to-validity}")
            < main.index("\\input{sections/conclusion}"))
    assert await manuscripts.get_text(session, m.id, path) == "\\section{Threats to validity}\n\n"
    snaps = await manuscript_history.list_(session, m.id)
    assert snaps[0].reason == "before_sections" and "sections/threats-to-validity.tex" not in snaps[0].files


async def test_a_refused_operation_writes_nothing(session):
    m = await new(session)
    before = await main_of(session, m.id)
    with pytest.raises(InvalidInput, match="not_a_section"):
        await ops.delete(session, m.id, "sections/nope.tex")
    with pytest.raises(InvalidInput, match="bad_title"):
        await ops.add(session, m.id, title="", after=None)
    with pytest.raises(InvalidInput, match="not_a_section"):
        await ops.add(session, m.id, title="X", after="sections/nope.tex")
    with pytest.raises(InvalidInput, match="no_sections"):
        await ops.split_main(session, m.id)  # already split: no \section left in main
    assert await main_of(session, m.id) == before
    assert await manuscript_history.list_(session, m.id) == []


async def test_retitle_renames_and_rewrites_the_input(session):
    m = await new(session)
    new_path = await ops.retitle(session, m.id, "sections/method.tex", title="Methods")
    assert new_path == "sections/methods.tex"
    assert await manuscripts.get_text(session, m.id, "sections/method.tex") is None
    assert (await manuscripts.get_text(session, m.id, new_path)).startswith("\\section{Methods}")
    main = await main_of(session, m.id)
    assert "\\input{sections/methods}" in main and "sections/method}" not in main


async def test_retitle_never_collides_with_another_section(session):
    m = await new(session)
    path = await ops.retitle(session, m.id, "sections/method.tex", title="Results")
    assert path == "sections/results-2.tex"
    assert inputs(await main_of(session, m.id)).count("\\input{sections/results}") == 1
    same = await ops.retitle(session, m.id, "sections/results.tex", title="Results")
    assert same == "sections/results.tex"  # its own name is not "taken"


async def test_move_reorders(session):
    m = await new(session)
    await ops.move(session, m.id, "sections/results.tex", to=0)
    assert inputs(await main_of(session, m.id))[0] == "\\input{sections/results}"


async def test_delete_then_restore_brings_it_back(session):
    m = await new(session)
    before = await main_of(session, m.id)
    await ops.delete(session, m.id, "sections/method.tex")
    assert await manuscripts.get_text(session, m.id, "sections/method.tex") is None
    assert "sections/method}" not in await main_of(session, m.id)
    snaps = await manuscript_history.list_(session, m.id)
    await manuscript_history.restore(session, m.id, snaps[0].id)
    assert await manuscripts.get_text(session, m.id, "sections/method.tex") is not None
    assert await main_of(session, m.id) == before


async def test_split_main_of_a_single_file_paper(session):
    main = ("\\documentclass{article}\n\\begin{document}\n\\section{One}\nA\n\\section{Two}\nB\n"
            "\\bibliography{refs}\n\\end{document}\n")
    m = await manuscripts.create_from_files(session, title="P", workspace_id=None, files={"main.tex": main},
                                            main_file="main.tex")
    assert await ops.split_main(session, m.id) == ["sections/one.tex", "sections/two.tex"]
    assert inputs(await main_of(session, m.id)) == ["\\input{sections/one}", "\\input{sections/two}"]
    assert await manuscripts.get_text(session, m.id, "sections/two.tex") == "\\section{Two}\nB\n"
    assert (await manuscript_history.list_(session, m.id))[0].reason == "before_sections"


async def test_split_main_refuses_to_overwrite_an_existing_file(session):
    main = "\\begin{document}\n\\section{One}\nA\n\\end{document}\n"
    m = await manuscripts.create_from_files(session, title="P", workspace_id=None,
                                            files={"main.tex": main, "sections/one.tex": "mine"}, main_file="main.tex")
    with pytest.raises(Conflict, match="file_exists"):
        await ops.split_main(session, m.id)
    assert await manuscripts.get_text(session, m.id, "sections/one.tex") == "mine"
    assert await manuscript_history.list_(session, m.id) == []


async def test_an_operation_makes_an_open_main_stale(session):
    m = await new(session)
    base = (await manuscripts.read(session, m.id, "main.tex")).updated_at
    await ops.add(session, m.id, title="New", after=None)
    with pytest.raises(Conflict, match="file_changed"):
        await manuscripts.save_text(session, m.id, "main.tex", "old buffer", base=base)
