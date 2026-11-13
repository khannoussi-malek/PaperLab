"""The reader's skills as MCP prompts (M17.5): the names, arguments and the one user message. Pure, and free of MCP
types (mcp_server/server.py imports only app.core and turns these into the library's Prompt objects)."""

from typing import NamedTuple

from app.core.skills import SkillView

ARGUMENTS = {"paper": ("paper_id",), "workspace": ("workspace",), "both": ("paper_id", "workspace")}
REQUIRED = {"paper": ("paper_id",), "workspace": ("workspace",), "both": ()}
PAPER_TAIL = (
    'Work on the paper "{title}" (PaperLab paper id {id}). Gather the passages you need with PaperLab\'s tools '
    "(search_library, get_paper) and quote or cite what you use."
)
WORKSPACE_TAIL = (
    'Work on the papers in the PaperLab workspace "{name}". Gather the passages you need with PaperLab\'s tools '
    "(list_papers, search_library, get_paper) and quote or cite what you use."
)


ARGUMENT_HELP = {
    "paper_id": "The PaperLab id of the paper (from search_library or list_papers).",
    "workspace": "The name of a PaperLab workspace (from list_workspaces).",
}


def prompt_name(view: SkillView) -> str:
    """A bundled skill's slug (check-evaluation); a custom one's custom-<uuid>."""
    kind, _, key = view.id.partition(":")
    return key if kind == "builtin" else f"custom-{key}"


class Argument(NamedTuple):
    name: str
    description: str
    required: bool


def prompt_args(scope: str) -> list[Argument]:
    return [Argument(name, ARGUMENT_HELP[name], name in REQUIRED[scope]) for name in ARGUMENTS[scope]]


def prompt_text(view: SkillView, *, paper: tuple[str, str] | None, workspace: str | None) -> str:
    """The skill's instructions, then one line naming the paper (title, id) or the workspace."""
    if paper is not None:
        title, paper_id = paper
        tail = PAPER_TAIL.format(title=title, id=paper_id)
    else:
        tail = WORKSPACE_TAIL.format(name=workspace)
    return f"{view.instructions}\n\n{tail}"
