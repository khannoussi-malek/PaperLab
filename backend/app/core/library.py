"""The library as an MCP client reads it: passages for a question, and a paper's card. IDs and structure, never prose.

Each function returns plain dataclasses; the MCP server returns them as they are (M6, D93).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import embedding_index, workspaces
from app.core.errors import InvalidInput
from app.core.notes import list_notes_for_paper
from app.core.papers import get_paper
from app.core.retrieval import MAX_PER_PAPER, retrieve
from app.models import Chunk, Paper, Workspace, workspace_papers

SEARCH_K = 8


@dataclass(frozen=True)
class Passage:
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    year: int | None
    page: int
    section: str | None
    text: str
    distance: float


@dataclass(frozen=True)
class Section:
    title: str
    page: int  # where the section starts


@dataclass(frozen=True)
class NoteBrief:
    id: uuid.UUID
    provenance: str  # human | llm | llm_edited: an AI note must never be quoted as the owner's own words (D90)
    body: str
    page: int  # its first anchor on this paper
    quoted_text: str


@dataclass(frozen=True)
class PaperCard:
    id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    abstract: str | None
    status: str
    page_count: int | None
    is_retracted: bool
    workspaces: list[str]  # names, alphabetical
    sections: list[Section]  # in reading order
    notes: list[NoteBrief]  # in reading order


async def search(
    session: AsyncSession, query: str, workspace: str | None = None, *, k: int = SEARCH_K, embedder=None
) -> list[Passage]:
    """The k passages nearest to the query, closest first, at most MAX_PER_PAPER from one paper, in the whole library
    or one workspace (by name). The name is checked before anything is embedded, so a wrong one never loads the model.

    Raises InvalidInput("empty_query"), NotFound("unknown_workspace", available=[...]),
    Conflict("embedding_model_changed").
    """
    if not query.strip():
        raise InvalidInput("empty_query")
    if workspace is None:
        workspace_id, scope = None, await embedding_index.indexed_papers(session)
    else:
        workspace_id = await workspaces.by_name(session, workspace)
        scope = [paper.id for paper in await workspaces.papers(session, workspace_id)]
    await embedding_index.check_model(session, settings.embed_model, scope)
    found = await retrieve(
        session, query, workspace_id=workspace_id, k=k, embedder=embedder, per_paper=MAX_PER_PAPER
    )
    titles = await session.execute(
        select(Paper.id, Paper.title, Paper.year).where(Paper.id.in_({chunk.paper_id for chunk in found}))
    )
    papers = {paper_id: (title, year) for paper_id, title, year in titles}
    return [
        Passage(
            chunk_id=chunk.id,
            paper_id=chunk.paper_id,
            paper_title=papers[chunk.paper_id][0],
            year=papers[chunk.paper_id][1],
            page=chunk.page,
            section=chunk.section,
            text=chunk.text,
            distance=round(chunk.distance, 4),
        )
        for chunk in found
    ]


async def paper_card(session: AsyncSession, paper_id: uuid.UUID) -> PaperCard:
    """A paper's metadata, its section outline, its workspaces and every note on it with its provenance. No chunk text:
    search gives passages. Raises NotFound."""
    paper = await get_paper(session, paper_id)
    names = select(Workspace.name).join(workspace_papers).where(workspace_papers.c.paper_id == paper_id)
    starts = await session.execute(
        select(Chunk.section_title, Chunk.page).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    )
    sections: dict[str, Section] = {}
    for title, page in starts:
        if title and title not in sections:
            sections[title] = Section(title=title, page=page)
    notes = []
    for note in await list_notes_for_paper(session, paper_id):
        here = [anchor for anchor in note.anchors if anchor.paper_id == paper_id]
        first = min(here, key=lambda anchor: (anchor.page, min(rect[1] for rect in anchor.bbox)))
        notes.append(NoteBrief(note.id, note.provenance, note.body, first.page, first.quoted_text))
    return PaperCard(
        id=paper.id,
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        abstract=paper.abstract,
        status=paper.status,
        page_count=paper.page_count,
        is_retracted=paper.is_retracted,
        workspaces=sorted(await session.scalars(names)),
        sections=list(sections.values()),
        notes=notes,
    )
