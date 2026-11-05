"""The library as an MCP client reads it: passages for a question, and a paper's card. IDs and structure, never prose.

Each function returns plain dataclasses; the MCP server returns them as they are (M6, D93).
"""

import uuid
from dataclasses import dataclass, field
from itertools import accumulate
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import embedding_index, workspaces
from app.core import tags as tag_store
from app.core.candidates import normal_title
from app.core.enrichment import normalize_doi
from app.core.errors import InvalidInput, NotFound
from app.core.notes import list_notes_for_paper
from app.core.papers import ABSTRACT_PAGE, get_paper
from app.core.retrieval import MAX_PER_PAPER, retrieve, searchable
from app.models import Chunk, Paper, Workspace, workspace_papers

SEARCH_K = 8
# read_pages: a page range an agent can hold at once. A section is read by going on from `next_page`.
MAX_READ_PAGES = 10
MAX_READ_CHARS = 20_000
# A paper card's outline. Past this a long file's outline floods the client: 10,559 titles were 664,000 characters.
MAX_OUTLINE_SECTIONS = 300
MAX_LIMIT = 50
COPY_OVERFETCH = 4  # a few more than asked for, so collapsing copies doesn't leave the answer short
SAME_PASSAGE = 0.8  # share of words in common at which two copies' chunks count as one passage


@dataclass(frozen=True)
class Passage:
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    year: int | None
    page: int | None  # None for an abstract (from_abstract): cite it as the paper's abstract, never by page
    section: str | None
    text: str
    distance: float
    source_type: (
        str | None
    )  # its paper's: journal_article, proceedings, book, chapter, preprint, magazine, thesis, other
    peer_reviewed: str  # true | false | unknown (a heuristic; the owner can set it)
    published_venue: str | None  # where a preprint was published, when known
    evidence_access: str  # full_text | abstract | metadata
    from_abstract: bool  # a paper saved without a PDF: its abstract, with no page to cite
    also_in: list[uuid.UUID] = field(default_factory=list)  # other copies of this paper with the same passage


@dataclass(frozen=True)
class Section:
    title: str
    page: int  # where the section starts


@dataclass(frozen=True)
class NoteBrief:
    id: uuid.UUID
    provenance: str  # human | llm | llm_edited: an AI note must never be quoted as the owner's own words (D90)
    body: str
    page: int | None  # its first passage on this paper; None for a note on the whole paper
    quoted_text: str | None


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
    source_type: str | None
    peer_reviewed: str
    evidence_access: str
    published_doi: str | None  # a preprint's published version, when known
    published_venue: str | None
    reading_pass: int
    triage: str | None
    workspaces: list[str]  # names, alphabetical
    sections: list[Section]  # in reading order, at most MAX_OUTLINE_SECTIONS
    sections_total: int
    notes: list[NoteBrief]  # notes on the whole paper first, newest first; then in reading order


def _same_work(one: Paper, other: Paper) -> bool:
    """One's a published version the other names, or they carry one title."""
    a, b = (one.doi or "").lower(), (other.doi or "").lower()
    if (a and a == (other.published_doi or "").lower()) or (b and b == (one.published_doi or "").lower()):
        return True
    return normal_title(one.title) == normal_title(other.title)


def _same_passage(one: str, other: str) -> bool:
    a, b = set(one.lower().split()), set(other.lower().split())
    return bool(a and b) and len(a & b) / len(a | b) >= SAME_PASSAGE


def _collapse_copies(found: list, papers: dict[uuid.UUID, Paper]) -> tuple[list, dict[uuid.UUID, list[uuid.UUID]]]:
    """A preprint and its published copy answer with one passage twice: the better match stays, naming the other."""
    kept: list = []
    also: dict[uuid.UUID, list[uuid.UUID]] = {}
    for chunk in found:
        twin = next(
            (
                k for k in kept
                if k.paper_id != chunk.paper_id and _same_work(papers[k.paper_id], papers[chunk.paper_id])
                and _same_passage(k.text, chunk.text)
            ),
            None,
        )
        if twin is None:
            kept.append(chunk)
        else:
            also.setdefault(twin.id, []).append(chunk.paper_id)
    return kept, also


async def _one_paper(session: AsyncSession, paper_id: uuid.UUID | None, doi: str | None) -> uuid.UUID | None:
    """The single paper a search is scoped to, or None. Raises for both given, or one the library doesn't hold."""
    if paper_id is not None and doi:
        raise InvalidInput("paper_or_doi", detail="Give a paper_id or a doi, not both.")
    if paper_id is not None:
        found = (await session.get(Paper, paper_id)) is not None
    elif doi:
        wanted = normalize_doi(doi) or doi.strip().lower()
        paper_id = await session.scalar(select(Paper.id).where(func.lower(Paper.doi) == wanted))
        found = paper_id is not None
    else:
        return None
    if not found:
        raise NotFound("paper_not_in_library", detail=f"{doi or paper_id} is not in the library.")
    return paper_id


async def search(
    session: AsyncSession, query: str, workspace: str | None = None, *, limit: int = SEARCH_K, embedder=None,
    tags: list[str] | None = None, match: Literal["any", "all"] = "any",
    paper_id: uuid.UUID | None = None, doi: str | None = None,
) -> list[Passage]:
    """The `limit` passages that best match the query, best first, at most MAX_PER_PAPER from one paper, in the whole
    library or one workspace (by name). `paper_id` or `doi` keeps the search on that one paper, with no per-paper limit.
    A passage a preprint and its published copy both hold comes once, its `also_in` naming the other. The name is
    checked before anything is embedded, so a wrong one never loads the model.

    `tags` (a workspace's tag names) keeps only papers carrying any/all of them. Raises
    InvalidInput("empty_query" | "tags_need_a_workspace" | "unknown_tag" | "invalid_match" | "paper_or_doi" |
    "invalid_limit"), NotFound("unknown_workspace", available=[...]), NotFound("paper_not_in_library"),
    Conflict("search_not_set_up" | "search_rebuilding", detail=<sentence>, …), Conflict("embedding_model_changed"), or
    Conflict(<the question can't be embedded>).
    """
    if not query.strip():
        raise InvalidInput("empty_query")
    if tags and workspace is None:
        raise InvalidInput("tags_need_a_workspace")
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidInput("invalid_limit", detail=f"limit must be 1 to {MAX_LIMIT}.")
    one_paper = await _one_paper(session, paper_id, doi)
    wanted = None
    if workspace is None:
        workspace_id, scope = None, await embedding_index.indexed_papers(session)
    else:
        workspace_id = await workspaces.by_name(session, workspace)
        wanted = await tag_store.paper_ids(session, workspace_id, tags, match)
        scope = [paper.id for paper in await workspaces.papers(session, workspace_id)]
        if wanted is not None:  # retrieve takes paper_ids or workspace_id, never both
            scope, workspace_id = [p for p in scope if p in wanted], None
    if one_paper is not None:  # within the workspace or tags, when given too
        scope, workspace_id, wanted = [p for p in scope if p == one_paper] or (
            [one_paper] if workspace is None else []
        ), None, {one_paper}
    if wanted is not None and not scope:
        return []
    embedder = await searchable(session, scope, embedder)  # not set up, then rebuilding, then stale vectors (D156)
    found = await retrieve(
        session, query, workspace_id=workspace_id, paper_ids=scope if wanted is not None else None,
        k=limit if one_paper is not None else limit + COPY_OVERFETCH, embedder=embedder,
        per_paper=limit if one_paper is not None else MAX_PER_PAPER,
    )
    rows = await session.scalars(
        select(Paper).where(Paper.id.in_({chunk.paper_id for chunk in found})).execution_options(populate_existing=True)
    )
    papers = {paper.id: paper for paper in rows}
    found, also = _collapse_copies(found, papers)
    return [
        Passage(
            chunk_id=chunk.id,
            paper_id=chunk.paper_id,
            paper_title=papers[chunk.paper_id].title,
            year=papers[chunk.paper_id].year,
            page=None if chunk.from_abstract else chunk.page,
            section=chunk.section,
            text=f"(abstract only) {chunk.text}" if chunk.from_abstract else chunk.text,
            distance=round(chunk.distance, 4),
            source_type=papers[chunk.paper_id].source_type,
            peer_reviewed=papers[chunk.paper_id].peer_reviewed,
            published_venue=papers[chunk.paper_id].published_venue,
            evidence_access=papers[chunk.paper_id].evidence_access,
            from_abstract=chunk.from_abstract,
            also_in=also.get(chunk.id, []),
        )
        for chunk in found[:limit]
    ]


@dataclass(frozen=True)
class PagePassage:
    chunk_id: uuid.UUID
    page: int
    section: str | None
    text: str


@dataclass(frozen=True)
class PagesRead:
    passages: list[PagePassage]
    next_page: int | None  # where to go on from; None at the end of the paper


async def read_pages(session: AsyncSession, paper_id: uuid.UUID, page: int, pages: int = 1) -> PagesRead:
    """The paper's passages on `page` and the `pages` - 1 after it, in reading order, up to MAX_READ_CHARS: the "read"
    half of locate-then-read. Passages are never split, and the first is always given. Raises NotFound,
    InvalidInput("invalid_pages")."""
    await get_paper(session, paper_id)
    if page < 1 or not 1 <= pages <= MAX_READ_PAGES:
        raise InvalidInput("invalid_pages", detail=f"page starts at 1, and pages must be 1 to {MAX_READ_PAGES}.")
    in_paper = select(Chunk.id, Chunk.page, Chunk.section_title, Chunk.text).where(Chunk.paper_id == paper_id)
    in_range = in_paper.where(Chunk.page >= page, Chunk.page < page + pages).order_by(Chunk.ordinal)
    rows = (await session.execute(in_range)).all()
    totals = accumulate(len(row.text) for row in rows)
    kept = [row for row, total in zip(rows, totals) if total <= MAX_READ_CHARS] or rows[:1]
    if len(kept) < len(rows):
        next_page = rows[len(kept)].page
    else:
        after = select(func.min(Chunk.page)).where(Chunk.paper_id == paper_id, Chunk.page >= page + pages)
        next_page = await session.scalar(after)
    return PagesRead([PagePassage(r.id, r.page, r.section_title, r.text) for r in kept], next_page)


async def paper_card(session: AsyncSession, paper_id: uuid.UUID) -> PaperCard:
    """A paper's metadata, its section outline, its workspaces and every note on it with its provenance. No chunk text:
    search gives passages. Raises NotFound."""
    paper = await get_paper(session, paper_id)
    await session.refresh(paper)  # evidence_access reads chunks, which a bulk write may have changed behind this object
    names = select(Workspace.name).join(workspace_papers).where(workspace_papers.c.paper_id == paper_id)
    starts = await session.execute(
        select(Chunk.section_title, Chunk.page)
        .where(Chunk.paper_id == paper_id, Chunk.page != ABSTRACT_PAGE)  # the abstract is a field, not a section
        .order_by(Chunk.ordinal)
    )
    sections: dict[str, Section] = {}
    for title, page in starts:
        if title and title not in sections:
            sections[title] = Section(title=title, page=page)
    notes = []
    for note in await list_notes_for_paper(session, paper_id):
        here = [anchor for anchor in note.anchors if anchor.paper_id == paper_id]
        first = min(here, key=lambda anchor: (anchor.page, min(rect[1] for rect in anchor.bbox)), default=None)
        page, quote = (None, None) if first is None else (first.page, first.quoted_text)
        notes.append(NoteBrief(note.id, note.provenance, note.body, page, quote))
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
        source_type=paper.source_type,
        peer_reviewed=paper.peer_reviewed,
        evidence_access=paper.evidence_access,
        published_doi=paper.published_doi,
        published_venue=paper.published_venue,
        reading_pass=paper.reading_pass,
        triage=paper.triage,
        workspaces=sorted(await session.scalars(names)),
        sections=list(sections.values())[:MAX_OUTLINE_SECTIONS],
        sections_total=len(sections),
        notes=notes,
    )
