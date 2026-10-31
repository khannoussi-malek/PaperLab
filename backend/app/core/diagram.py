"""Diagrams (M27 slice E): draw a TikZ picture from the researcher's own description. The model may draw only what the
description names, in the researcher's words; `diagram_tikz.check` judges the code and `labels_not_in_description`
flags any label the researcher never wrote. Problems come back with the code, never raised, so the row can show it.

A tagged block, not JSON: backslashes inside JSON strings are what small local models get wrong."""

import re
from dataclasses import dataclass

from app.core import diagram_tikz, prompts

PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("diagram", PROMPT_VERSION).split("\n<!-- prompt -->\n")
MAX_DESCRIPTION = 2_000
MODEL_ERROR = "model_error"
RETRY = (
    "\n\nYour reply had no <tikz> block. Reply again with only the block: <tikz>, any \\usetikzlibrary lines, "
    "one tikzpicture, </tikz>."
)
_BLOCK = re.compile(r"<tikz>(.*?)</tikz>", re.S | re.I)
_FENCE = re.compile(r"^```[A-Za-z]*\n|\n?```$")


@dataclass(frozen=True)
class Generated:
    libraries: list[str]
    picture: str
    errors: list[str]  # plain-language guard problems; empty when insertable
    labels_not_in_description: list[str]
    model: str


class DiagramFailed(Exception):
    pass


def build_prompt(description: str) -> str:
    return PROMPT_TEMPLATE.format(description=description.strip(), libraries=", ".join(diagram_tikz.ALLOWED_LIBRARIES))


def parse_reply(reply: str) -> str | None:
    """The first `<tikz>…</tikz>` body, a code fence inside it removed; None when there is no non-empty block."""
    m = _BLOCK.search(reply)
    body = _FENCE.sub("", m.group(1).strip()).strip() if m else ""
    return body or None


async def generate(description: str, *, llm) -> Generated:
    """One call, and one retry with the reason when the reply has no block. Raises DiagramFailed only then."""
    prompt = build_prompt(description)
    for attempt in (prompt, prompt + RETRY):
        code = parse_reply("".join([t async for t in llm.stream(SYSTEM_PROMPT, attempt)]))
        if code is not None:
            libraries, picture = diagram_tikz.split_code(code)
            return Generated(
                libraries,
                picture,
                diagram_tikz.check(libraries, picture),
                diagram_tikz.labels_not_in_description(picture, description),
                getattr(llm, "model", "unknown"),
            )
    raise DiagramFailed(MODEL_ERROR)
