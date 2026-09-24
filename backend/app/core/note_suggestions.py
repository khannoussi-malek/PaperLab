"""Suggests notes for one paper: short, cited summaries of a handful of its passages, spread across the whole
paper rather than clustered around a query (there's no question here to retrieve against).

Never writes a note itself — same human-in-the-loop rule chat.py's own docstring states for it. A suggestion is
just a body plus the one chunk it's grounded in; the caller decides whether to store the generation as an
LLMOutput (so an accepted suggestion can be promoted through notes.promote_llm_fragment, same as a chat answer's
selection) and whether/how to show it to the user.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import prompts
from app.core.chat import chunk_sources, format_context
from app.core.errors import Conflict
from app.core.notes import list_notes_for_paper
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, LLMOutput, PaperStatus
from app.providers.base import LLM

NOTE_SUGGESTIONS_PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("note_suggestions", NOTE_SUGGESTIONS_PROMPT_VERSION).split(
    "\n<!-- prompt -->\n"
)
# A handful of cards, not one per chunk in a long paper — SUGGEST_K spread evenly across it (see _sample_evenly).
SUGGEST_K = 6
_SUGGESTION_LINE = re.compile(r"^\[C(\d+)\]:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class NoteSuggestion:
    body: str
    source: RetrievedChunk  # the one chunk this note is grounded in


@dataclass(frozen=True)
class Suggested:
    suggestions: list[NoteSuggestion]
    content: str  # the raw model output, for save_suggestions to store verbatim
    sources: list[RetrievedChunk]  # every passage sent to the model, sampled[i-1] is [C{i}] in `content`


def _sample_evenly(chunks: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
    """k chunks spread first-to-last across the paper — representative coverage of every section instead of
    clustering around whichever passages a query-based retrieval would favor, since there's no question here to
    retrieve against."""
    if len(chunks) <= k:
        return chunks
    step = len(chunks) / k
    indices = dict.fromkeys(int(i * step) for i in range(k))  # dict.fromkeys: dedupe, keep order
    return [chunks[i] for i in indices]


def _spot(page: int, bbox: list) -> tuple:
    """A location on the page, hashable. The only reliable "is this already noted" signal available: note_anchors
    has a chunk_id column, but nothing that writes an anchor (promote_llm_fragment included) ever populates it —
    every anchor is created keyed on (page, bbox) instead, so that's what a repeat suggestion has to match too."""
    return (page, tuple(tuple(rect) for rect in bbox))


async def _already_noted(session: AsyncSession, paper_id: uuid.UUID) -> set[tuple]:
    notes = await list_notes_for_paper(session, paper_id)
    return {_spot(a.page, a.bbox) for note in notes for a in note.anchors}


async def suggest(session: AsyncSession, paper_id: uuid.UUID, llm: LLM) -> Suggested:
    """Raises NotFound, or Conflict("paper_not_ready" | "paper_not_indexed"). Skips any passage a note (human or
    AI, from an earlier accepted suggestion or written by hand) already covers — asking again shouldn't keep
    re-suggesting the same spots, and there's nothing useful left to say about one that already has a note."""
    paper = await get_paper(session, paper_id)
    if paper.status != PaperStatus.READY:
        raise Conflict("paper_not_ready")
    all_chunks = await chunk_sources(session, Chunk.paper_id == paper_id)
    if not all_chunks:
        raise Conflict("paper_not_indexed")
    already_noted = await _already_noted(session, paper_id)
    candidates = [c for c in all_chunks if _spot(c.page, c.bbox) not in already_noted]
    if not candidates:  # every passage already has a note covering it
        return Suggested(suggestions=[], content="", sources=[])
    sample = _sample_evenly(candidates, SUGGEST_K)
    prompt = PROMPT_TEMPLATE.format(context=format_context(paper, sample))
    content = "".join([text async for text in llm.stream(SYSTEM_PROMPT, prompt)])

    suggestions = []
    for match in _SUGGESTION_LINE.finditer(content):
        index, body = int(match.group(1)), match.group(2).strip()
        if body and 1 <= index <= len(sample):
            suggestions.append(NoteSuggestion(body=body, source=sample[index - 1]))
    return Suggested(suggestions=suggestions, content=content, sources=sample)


async def save_suggestions(
    session: AsyncSession, paper_id: uuid.UUID, suggested: Suggested, model: str, connection_name: str
) -> uuid.UUID:
    """Stores the raw generation as an LLMOutput, kind="note_suggestions" (never "chat" — so it never shows up
    in the paper's chat history). Returns its id: what an accepted suggestion promotes through, via the exact
    same notes.promote_llm_fragment a chat answer's own selection already uses — accepting one of these needs no
    new write path, just POST /api/notes/promote with this output_id, the suggestion's body, and its chunk id."""
    output = LLMOutput(
        paper_id=paper_id,
        kind="note_suggestions",
        content=suggested.content,
        source_chunks=[c.id for c in suggested.sources],
        cited_chunks=[s.source.id for s in suggested.suggestions],
        model=model,
        connection_name=connection_name,
        prompt_version=NOTE_SUGGESTIONS_PROMPT_VERSION,
    )
    session.add(output)
    await session.commit()
    return output.id
