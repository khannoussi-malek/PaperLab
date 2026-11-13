"""AI number suggestions (D33, the AI half of M13's numbers from text). The model lists a section's numbers with a
quote each; PaperLab keeps a suggestion only when its quote is in that section, its value is in its quote, and the
quote sits in one place in the paper, which gives the value its page and rects. Nothing is saved here: the reader adds
the ones they want, and an added number's label is marked as the model's (`capture.add_number(suggested=True)`).
"""

import re
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import notes, prompts, quotes
from app.core.datasets import Rect
from app.core.errors import DomainError, InvalidInput
from app.core.llm_json import ask_json
from app.core.numbers import parse_number
from app.core.papers import list_chunks

PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("number_suggest", PROMPT_VERSION).split("\n<!-- prompt -->\n")
SECTION_CHARS = 12_000  # ponytail: a longer section is cut; ask again on a shorter part if numbers go missing
MAX_SUGGESTIONS = 20


class _Number(BaseModel):
    label: str = Field(max_length=200)
    value: str = Field(max_length=60)
    unit: str = Field(default="", max_length=40)
    quote: str = Field(max_length=600)


class _Reply(BaseModel):
    numbers: list[_Number] = Field(default_factory=list, max_length=60)


@dataclass(frozen=True)
class Suggestion:
    label: str
    raw: str
    unit: str
    quote: str
    page: int
    bbox: list[Rect]


@dataclass(frozen=True)
class Suggestions:
    suggestions: list[Suggestion]
    dropped: int  # suggestions the checks threw out: a quote not in the section, a value not in its quote, ...


def render_prompt(title: str | None, text: str) -> str:
    values = {"title": title or "(before the first heading)", "text": text}
    return re.sub(r"\{(title|text)\}", lambda m: values[m.group(1)], PROMPT_TEMPLATE)


async def _keep(session: AsyncSession, paper_id: uuid.UUID, number: _Number, section: str) -> Suggestion | None:
    if parse_number(number.value).value is None or not number.label.strip():
        return None
    if quotes.fold(number.value) not in quotes.fold(number.quote):
        return None
    if not quotes.check_quotes([number.quote], [section], 1)[0]:
        return None
    try:
        anchor = await notes.locate_quote(session, paper_id, number.quote)
    except DomainError:  # not found as one passage, or found twice: no single place to anchor it
        return None
    return Suggestion(number.label.strip(), number.value.strip(), number.unit.strip(), number.quote.strip(),
                      anchor.page, [tuple(rect) for rect in anchor.bbox])  # fmt: skip


async def suggest(session: AsyncSession, paper_id: uuid.UUID, section_title: str | None, llm) -> Suggestions:
    """Raises NotFound (the paper), InvalidInput("unknown_section") when no chunk has that heading."""
    chunks = [c for c in await list_chunks(session, paper_id) if c.section_title == section_title]
    if not chunks:
        raise InvalidInput("unknown_section")
    section = "\n\n".join(c.text for c in chunks)[:SECTION_CHARS]
    await session.commit()  # hold no transaction while the model reads
    reply = await ask_json(llm, SYSTEM_PROMPT, render_prompt(section_title, section), _Reply)
    asked = reply.numbers if reply else []
    kept: list[Suggestion] = []
    seen: set[tuple[str, int]] = set()
    for number in asked:
        found = await _keep(session, paper_id, number, section)
        if found is not None and (found.raw, found.page) not in seen and len(kept) < MAX_SUGGESTIONS:
            seen.add((found.raw, found.page))
            kept.append(found)
    return Suggestions(kept, len(asked) - len(kept))
