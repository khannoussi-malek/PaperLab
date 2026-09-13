"""Prompt files live in backend/prompts/<name>.v<N>.md; the version is stored in llm_outputs.prompt_version."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load(name: str, version: int) -> str:
    """Raises FileNotFoundError naming the missing <name>.v<N>.md."""
    return (PROMPTS_DIR / f"{name}.v{version}.md").read_text()
