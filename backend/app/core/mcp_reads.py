"""The MCP read tools' answers (M28): references, captured tables and saved answers, shaped for a client's model.

Each function wraps one existing core service and only reshapes what it returns: it caps long lists and renames a
missing id to the code the tools answer with. Nothing here fetches from the network.
"""

import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import chat, datasets, references, workspaces
from app.core.datasets import CellView
from app.core.errors import Gone, InvalidInput, NotFound
from app.core.papers import ABSTRACT_PAGE

REFERENCE_ROWS = 100
DATASET_ROWS = 200
ANSWERS_PER_CALL = 20
# The tool's direction words, and the core's (references.py stores them as "cites" and "cited_by").
DIRECTIONS = {"references": "cites", "citing": "cited_by"}
UNFETCHED = "Not fetched yet: the owner can fetch them from the paper's References tab."


@dataclass(frozen=True)
class ReferenceOut:
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    in_library: bool
    library_paper_id: uuid.UUID | None
    cocitation: int
    cited_by_count: int | None


@dataclass(frozen=True)
class ReferencesOut:
    state: str
    error: str | None
    direction: str
    summary: references.Summary
    total: int
    truncated: bool
    rows: list[ReferenceOut]
    note: str | None = None  # set when the listing was never fetched


@dataclass(frozen=True)
class DatasetItem:
    id: uuid.UUID
    name: str
    kind: str
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    row_count: int
    column_count: int
    created_at: datetime


@dataclass(frozen=True)
class DatasetColumnOut:
    name: str
    unit: str | None


@dataclass(frozen=True)
class ChartOut:
    id: uuid.UUID
    title: str


@dataclass(frozen=True)
class DatasetOut:
    id: uuid.UUID
    name: str
    kind: str
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    columns: list[DatasetColumnOut]
    rows: list[list[CellView]]  # cells in column order, as the API shows them
    truncated: bool
    charts: list[ChartOut]


@dataclass(frozen=True)
class SourceOut:
    label: str  # the marker the answer text cites ([C1])
    paper_id: uuid.UUID
    page: int | None  # null for an abstract, which has no page
    section: str | None


@dataclass(frozen=True)
class AnswerOut:
    id: uuid.UUID
    question: str | None
    content: str
    ai: bool  # always true: never pass a saved answer off as the owner's
    model: str
    skill_label: str | None
    lens: str  # the lens the answer read through: 'full' is the whole paper
    created_at: datetime
    sources: list[SourceOut]
    sources_missing: int  # sources a re-ingest replaced
    notes_used: int | None


@dataclass(frozen=True)
class AnswersOut:
    total: int
    answers: list[AnswerOut] = field(default_factory=list)


async def _renamed_not_found(code: str, call: Awaitable):
    """A missing paper or dataset, answered with the tool's own code. A merged paper (Gone) keeps its own answer."""
    try:
        return await call
    except Gone:
        raise
    except NotFound as exc:
        raise NotFound(code) from exc


async def references_out(session: AsyncSession, paper_id: uuid.UUID, direction: str) -> ReferencesOut:
    listing = await _renamed_not_found(
        "unknown_paper", references.listing(session, paper_id, DIRECTIONS[direction])
    )  # fmt: skip
    return ReferencesOut(
        state=listing.state,
        error=listing.error,
        direction=direction,
        summary=listing.summary,
        total=len(listing.rows),
        truncated=len(listing.rows) > REFERENCE_ROWS,
        rows=[_reference(row) for row in listing.rows[:REFERENCE_ROWS]],
        note=UNFETCHED if listing.state == "none" else None,
    )


def _reference(row: references.ReferenceRow) -> ReferenceOut:
    return ReferenceOut(
        title=row.title,
        authors=row.authors,
        year=row.year,
        venue=row.venue,
        doi=row.doi,
        arxiv_id=row.arxiv_id,
        in_library=row.paper_id is not None,
        library_paper_id=row.paper_id,
        cocitation=row.cocitation,
        cited_by_count=row.cited_by_count,
    )


async def datasets_out(session: AsyncSession, paper_id: uuid.UUID | None) -> list[DatasetItem]:
    found = await _renamed_not_found("unknown_paper", datasets.list_datasets(session, paper_id))
    return [
        DatasetItem(
            id=d.id,
            name=d.name,
            kind=d.kind,
            paper_id=d.paper_id,
            paper_title=d.paper_title,
            page=d.page,
            row_count=d.row_count,
            column_count=d.column_count,
            created_at=d.created_at,
        )
        for d in found
    ]


async def dataset_out(session: AsyncSession, dataset_id: uuid.UUID) -> DatasetOut:
    view = await _renamed_not_found("unknown_dataset", datasets.get_dataset(session, dataset_id))
    return DatasetOut(
        id=view.id,
        name=view.name,
        kind=view.kind,
        paper_id=view.paper_id,
        paper_title=view.paper_title,
        page=view.page,
        columns=[DatasetColumnOut(name=c.name, unit=c.unit) for c in view.columns],
        rows=[row.cells for row in view.rows[:DATASET_ROWS]],
        truncated=len(view.rows) > DATASET_ROWS,
        charts=[ChartOut(id=chart.id, title=chart.title) for chart in view.charts],
    )


async def answers_out(
    session: AsyncSession, *, paper_id: uuid.UUID | None, workspace: str | None, offset: int
) -> AnswersOut:
    """Newest first, ANSWERS_PER_CALL at a time from `offset`. Give exactly one of a paper id or a workspace name."""
    if (paper_id is None) == (workspace is None):
        raise InvalidInput("invalid_scope", detail="Give a paper_id or a workspace, not both and not neither.")
    target = (
        chat.Scope(workspace_id=await workspaces.by_name(session, workspace)) if workspace is not None else paper_id
    )
    newest = list(reversed(await _renamed_not_found("unknown_paper", chat.list_answers(session, target))))
    return AnswersOut(total=len(newest), answers=[_answer(a) for a in newest[offset : offset + ANSWERS_PER_CALL]])


def _answer(answer: chat.Answer) -> AnswerOut:
    output = answer.output
    return AnswerOut(
        id=output.id,
        question=output.question,
        content=output.content,
        ai=True,
        model=output.model,
        skill_label=output.skill_label,
        lens=output.lens,
        created_at=output.created_at,
        # the label is the chunk's position in the answer, so a skipped source keeps its number
        sources=[_source(i, chunk) for i, chunk in enumerate(answer.sources, start=1) if chunk is not None],
        sources_missing=sum(chunk is None for chunk in answer.sources),
        notes_used=output.notes_used,
    )


def _source(index: int, chunk) -> SourceOut:
    return SourceOut(
        label=f"C{index}",
        paper_id=chunk.paper_id,
        page=None if chunk.page == ABSTRACT_PAGE else chunk.page,
        section=chunk.section,
    )
