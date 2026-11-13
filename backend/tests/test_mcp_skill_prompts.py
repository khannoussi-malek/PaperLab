"""The reader's skills as MCP prompts (M17.5): listed from the same merged list as the chat picker, read fresh on every
call, and rendered into one user message. Tests go through the server object, as test_mcp_server does."""

import uuid
from contextlib import asynccontextmanager

import pytest
from mcp import Client

from app.core import skills, workspaces
from app.models import Paper
from mcp_server import server, skill_prompts

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's skills and workspaces share the dev database
BUNDLED = {skill.slug: skill for skill in skills.BUNDLED}
PAPER_SKILL = next(skill for skill in skills.BUNDLED if skill.scope == "paper")
BOTH_SKILL = next(skill for skill in skills.BUNDLED if skill.scope == "both")
PAPER_TAIL = (
    'Work on the paper "{title}" (PaperLab paper id {id}). Gather the passages you need with PaperLab\'s tools '
    "(search_library, get_paper) and quote or cite what you use."
)
WORKSPACE_TAIL = (
    'Work on the papers in the PaperLab workspace "{name}". Gather the passages you need with PaperLab\'s tools '
    "(list_papers, search_library, get_paper) and quote or cite what you use."
)


@pytest.fixture(autouse=True)
def prompts_use_the_test_session(session, monkeypatch):
    @asynccontextmanager
    async def test_session():
        yield session

    monkeypatch.setattr(server, "sessions", test_session)


def view_of(**fields) -> skills.SkillView:
    base = dict(
        id="builtin:check-evaluation",
        label="Check an evaluation",
        description="Checks it.",
        scope="paper",
        instructions="Check the evaluation.",
        version=1,
        is_listed=True,
        is_paper_default=False,
        is_workspace_default=False,
        state="builtin",
    )
    return skills.SkillView(**(base | fields))


async def listed() -> dict:
    async with Client(server.mcp) as client:
        return {prompt.name: prompt for prompt in (await client.list_prompts()).prompts}


async def fetch(name: str, arguments: dict | None = None):
    async with Client(server.mcp) as client:
        return await client.get_prompt(name, arguments)


async def make_paper(session, title: str) -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", status="ready", page_count=2)
    session.add(paper)
    await session.flush()
    return paper


def expected_arguments(scope: str) -> list[tuple[str, bool]]:
    return {
        "paper": [("paper_id", True)],
        "workspace": [("workspace", True)],
        "both": [("paper_id", False), ("workspace", False)],
    }[scope]


# Pure builder


async def test_a_bundled_skill_is_named_by_its_slug_and_a_custom_one_by_its_uuid():
    assert skill_prompts.prompt_name(view_of()) == "check-evaluation"
    assert skill_prompts.prompt_name(view_of(id="custom:abc", state="custom")) == "custom-abc"


@pytest.mark.parametrize("scope", ["paper", "workspace", "both"])
async def test_the_arguments_follow_the_scope(scope):
    arguments = skill_prompts.prompt_args(scope)
    assert [(argument.name, argument.required) for argument in arguments] == expected_arguments(scope)


async def test_the_paper_text_names_the_paper_and_the_paper_tools():
    text = skill_prompts.prompt_text(view_of(), paper=("A Title", "11111111"), workspace=None)
    assert text == "Check the evaluation.\n\n" + PAPER_TAIL.format(title="A Title", id="11111111")


async def test_the_workspace_text_names_the_workspace_and_the_workspace_tools():
    text = skill_prompts.prompt_text(view_of(scope="workspace"), paper=None, workspace="My thesis")
    assert text == "Check the evaluation.\n\n" + WORKSPACE_TAIL.format(name="My thesis")


# Listing


async def test_the_bundled_skills_are_listed_by_slug_with_their_label_and_arguments(session):
    prompts = await listed()

    bundled_names = {name for name in prompts if not name.startswith("custom-")}
    assert bundled_names == set(BUNDLED)
    for slug, skill in BUNDLED.items():
        prompt = prompts[slug]
        assert (prompt.title, prompt.description) == (skill.label, skill.description)
        assert [(argument.name, argument.required) for argument in prompt.arguments] == expected_arguments(skill.scope)


async def test_a_custom_skill_is_listed_as_custom_and_its_label_stands_in_for_an_empty_description(session):
    made = await skills.create(session, label=f"Probe {RUN}", description="", scope="paper", instructions="Probe.")

    prompt = (await listed())[f"custom-{made.id.split(':', 1)[1]}"]

    assert (prompt.title, prompt.description) == (f"Probe {RUN}", f"Probe {RUN}")


async def test_a_hidden_skill_leaves_the_list(session):
    await skills.update(session, f"builtin:{PAPER_SKILL.slug}", is_listed=False)

    assert PAPER_SKILL.slug not in await listed()


async def test_an_edit_shows_on_the_next_list(session):
    await skills.update(session, f"builtin:{PAPER_SKILL.slug}", label=f"Renamed {RUN}", description="")

    prompt = (await listed())[PAPER_SKILL.slug]

    assert (prompt.title, prompt.description) == (f"Renamed {RUN}", f"Renamed {RUN}")


async def test_a_reset_brings_the_shipped_skill_back_into_the_list(session):
    await skills.update(session, f"builtin:{PAPER_SKILL.slug}", label=f"Renamed {RUN}")
    await skills.reset(session, f"builtin:{PAPER_SKILL.slug}")

    assert (await listed())[PAPER_SKILL.slug].title == PAPER_SKILL.label


async def test_a_deleted_custom_skill_leaves_the_list(session):
    made = await skills.create(session, label=f"Gone {RUN}", description="d", scope="paper", instructions="Gone.")

    await skills.delete(session, made.id)

    assert f"custom-{made.id.split(':', 1)[1]}" not in await listed()


async def test_the_server_instructions_say_the_skills_are_prompts():
    async with Client(server.mcp) as client:
        assert "offered as prompts" in client.instructions


# Getting


async def test_a_paper_skill_gives_its_instructions_and_the_paper(session):
    paper = await make_paper(session, f"Prompt paper {RUN}")

    result = await fetch(PAPER_SKILL.slug, {"paper_id": str(paper.id)})

    [message] = result.messages
    assert message.role == "user"
    assert message.content.text == (
        f"{PAPER_SKILL.instructions}\n\n" + PAPER_TAIL.format(title=f"Prompt paper {RUN}", id=paper.id)
    )


async def test_an_edited_instruction_is_what_the_prompt_gives(session):
    paper = await make_paper(session, f"Edited paper {RUN}")
    await skills.update(session, f"builtin:{PAPER_SKILL.slug}", instructions="Use the new wording.")

    [message] = (await fetch(PAPER_SKILL.slug, {"paper_id": str(paper.id)})).messages

    assert message.content.text.startswith("Use the new wording.\n\n")


async def test_a_workspace_skill_gives_the_workspace_text(session):
    name = f"Prompt workspace {RUN}"
    await workspaces.create(session, name)
    made = await skills.create(
        session, label=f"Ws check {RUN}", description="d", scope="workspace", instructions="Check the workspace."
    )
    slug = f"custom-{made.id.split(':', 1)[1]}"

    [message] = (await fetch(slug, {"workspace": name})).messages

    assert message.content.text == "Check the workspace.\n\n" + WORKSPACE_TAIL.format(name=name)


async def test_a_both_skill_takes_a_paper_or_a_workspace(session):
    paper = await make_paper(session, f"Both paper {RUN}")
    name = f"Both workspace {RUN}"
    await workspaces.create(session, name)

    [by_paper] = (await fetch(BOTH_SKILL.slug, {"paper_id": str(paper.id)})).messages
    [by_workspace] = (await fetch(BOTH_SKILL.slug, {"workspace": name})).messages

    assert by_paper.content.text.startswith(f"{BOTH_SKILL.instructions}\n\nWork on the paper")
    assert by_workspace.content.text == f"{BOTH_SKILL.instructions}\n\n" + WORKSPACE_TAIL.format(name=name)


async def refused(name: str, arguments: dict | None = None) -> str:
    """The override's ValueError text. The client sees the library's generic internal error (see the wire test)."""
    with pytest.raises(ValueError) as caught:
        await server.mcp.get_prompt(name, arguments)
    return str(caught.value)


async def test_a_both_skill_with_neither_argument_is_refused(session):
    assert await refused(BOTH_SKILL.slug, {}) == "Give a paper_id or a workspace."


async def test_a_both_skill_with_both_arguments_is_refused(session):
    paper = await make_paper(session, f"Two ways {RUN}")
    arguments = {"paper_id": str(paper.id), "workspace": f"Two ways {RUN}"}
    assert await refused(BOTH_SKILL.slug, arguments) == "Give a paper_id or a workspace, not both."


async def test_a_paper_skill_without_its_argument_is_refused(session):
    assert await refused(PAPER_SKILL.slug, {}) == "Missing required arguments: {'paper_id'}"


async def test_a_paper_that_is_not_in_the_library_is_refused(session):
    missing = str(uuid.uuid4())
    assert await refused(PAPER_SKILL.slug, {"paper_id": missing}) == f"paper {missing} not found"


async def test_a_malformed_paper_id_is_refused(session):
    assert await refused(PAPER_SKILL.slug, {"paper_id": "not-a-uuid"}) == "paper_id is not a valid id."


async def test_an_unknown_workspace_is_refused(session):
    assert await refused(BOTH_SKILL.slug, {"workspace": f"No such workspace {RUN}"}) == "unknown_workspace"


async def test_a_hidden_skill_is_refused_by_name_although_chat_still_runs_it(session):
    await skills.update(session, f"builtin:{PAPER_SKILL.slug}", is_listed=False)
    paper = await make_paper(session, f"Hidden paper {RUN}")

    assert await refused(PAPER_SKILL.slug, {"paper_id": str(paper.id)}) == f"Unknown prompt: {PAPER_SKILL.slug}"


async def test_an_unknown_name_is_refused(session):
    assert await refused("no-such-skill", {}) == "Unknown prompt: no-such-skill"


async def test_the_existing_tools_still_list_after_the_prompts_were_added():
    async with Client(server.mcp) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert {"search_library", "get_paper", "list_papers", "list_workspaces"} <= names
