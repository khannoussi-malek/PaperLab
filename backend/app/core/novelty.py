"""P12: "Has this been done?" Ranks the user's own papers by closeness to a pasted idea. A ranking, not a verdict."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import embedding_index, library, workspaces
from app.core.errors import InvalidInput

MAX_CHARS = 6000
ABSTRACT_PREFIX = "(abstract only) "  # library.search adds it to abstract passages; the panel already says "abstract"
TOP = 10
# ponytail: uncalibrated guesses (cosine distance, lower = closer); retune on a real library with the real model.
# The source repo's 0.88/0.82 similarity cutoffs came from another corpus and model and are not used.
VERY_CLOSE = 0.25
RELATED = 0.45
NOTE = (
    "This only covers your own library ({n} papers searched). "
    "Finding nothing close here does not mean the idea is new."
)


@dataclass(frozen=True)
class NoveltyPaper:
    paper_id: uuid.UUID
    title: str
    year: int | None
    label: str  # very close | related | distant
    distance: float
    passage: str
    page: int | None  # None for an abstract
    section: str | None
    from_abstract: bool
    chunk_id: uuid.UUID


@dataclass(frozen=True)
class NoveltyReport:
    papers: list[NoveltyPaper]
    searched_papers: int
    note: str


def label_for(distance: float) -> str:
    return "very close" if distance <= VERY_CLOSE else "related" if distance <= RELATED else "distant"


async def _searched(session: AsyncSession, workspace: str | None) -> int:
    indexed = set(await embedding_index.indexed_papers(session))
    if workspace is None:
        return len(indexed)
    members = await workspaces.papers(session, await workspaces.by_name(session, workspace))
    return len([p for p in members if p.id in indexed])  # members with no chunks yet are not searched


async def check(
    session: AsyncSession, text: str, workspace: str | None = None, *, embedder=None
) -> NoveltyReport:
    """The TOP papers closest to `text`, each with its closest passage, in the whole library or one workspace (by name).
    Raises InvalidInput("empty_query" | "text_too_long") and whatever library.search raises."""
    text = text.strip()
    if len(text) > MAX_CHARS:
        raise InvalidInput("text_too_long", detail=f"Paste at most {MAX_CHARS} characters.")
    passages = await library.search(session, text, workspace, limit=library.MAX_LIMIT, embedder=embedder)
    best: dict[uuid.UUID, library.Passage] = {}
    for p in passages:  # search order is the fused rank, not distance: keep each paper's nearest
        if p.paper_id not in best or p.distance < best[p.paper_id].distance:
            best[p.paper_id] = p
    ranked = sorted(best.values(), key=lambda p: p.distance)[:TOP]
    papers = [
        NoveltyPaper(
            paper_id=p.paper_id, title=p.paper_title, year=p.year, label=label_for(p.distance), distance=p.distance,
            passage=p.text.removeprefix(ABSTRACT_PREFIX) if p.from_abstract else p.text, page=p.page, section=p.section, from_abstract=p.from_abstract, chunk_id=p.chunk_id,
        )
        for p in ranked
    ]
    searched = await _searched(session, workspace)
    return NoveltyReport(papers, searched, NOTE.format(n=searched))
