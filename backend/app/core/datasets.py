"""Datasets: tables of cells that charts read. A captured table, the numbers picked from a paper's text, or the owner's
own data.

Every cell keeps the text it was given (`raw`) and the number parsed from it. A cell read from the PDF is
`origin='extracted'`; when the owner changes it, `original_raw` keeps what extraction read, so the UI can mark it
edited. Rows and columns keep their ids across saves, because charts point at those ids.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.numbers import parse_number
from app.core.papers import get_paper
from app.models import Chart, Dataset, DatasetColumn, DatasetRow, Paper, cell_table, chart_datasets

Rect = tuple[float, float, float, float]

NAME_MAX_CHARS = 200
MAX_ROWS = 5_000
MAX_COLUMNS = 100
TABLE_EXTRACTOR = "words-grid-v1"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass(frozen=True)
class CellIn:
    raw: str
    # The text extraction read, for a cell that came from the PDF. None for a cell the owner typed.
    extracted: str | None = None
    page: int | None = None
    bbox: list[Rect] | None = None


@dataclass(frozen=True)
class ColumnIn:
    id: uuid.UUID | None  # None for a new column
    name: str
    unit: str | None


@dataclass(frozen=True)
class RowIn:
    id: uuid.UUID | None  # None for a new row
    cells: list[CellIn]  # one per column, in column order


@dataclass
class GridIn:
    columns: list[ColumnIn]
    rows: list[RowIn]


@dataclass(frozen=True)
class CellView:
    column_id: uuid.UUID
    raw: str
    value: float | None
    error: float | None
    origin: str
    original_raw: str | None
    page: int | None
    bbox: list[list[float]] | None


@dataclass(frozen=True)
class ColumnView:
    id: uuid.UUID
    position: int
    name: str
    unit: str | None


@dataclass(frozen=True)
class RowView:
    id: uuid.UUID
    position: int
    cells: list[CellView]  # in column order


@dataclass(frozen=True)
class ChartUse:
    id: uuid.UUID
    title: str
    column_ids: list[uuid.UUID]  # this dataset's columns the chart's spec names


@dataclass(frozen=True)
class DatasetSummary:
    id: uuid.UUID
    name: str
    kind: str
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    region: list[float] | None
    row_count: int
    column_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DatasetView(DatasetSummary):
    columns: list[ColumnView]
    rows: list[RowView]
    charts: list[ChartUse]


def clean_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= NAME_MAX_CHARS:
        raise InvalidInput(f"a name needs 1 to {NAME_MAX_CHARS} characters")
    return cleaned


async def _get(session: AsyncSession, dataset_id: uuid.UUID) -> Dataset:
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise NotFound(f"dataset {dataset_id} not found")
    return dataset


def _summaries_query():
    rows = select(func.count()).where(DatasetRow.dataset_id == Dataset.id).scalar_subquery()
    columns = select(func.count()).where(DatasetColumn.dataset_id == Dataset.id).scalar_subquery()
    return select(
        Dataset.id,
        Dataset.name,
        Dataset.kind,
        Dataset.paper_id,
        Paper.title,
        Dataset.page,
        Dataset.region,
        rows,
        columns,
        Dataset.created_at,
        Dataset.updated_at,
    ).outerjoin(Paper, Paper.id == Dataset.paper_id)


async def list_datasets(session: AsyncSession, paper_id: uuid.UUID | None = None) -> list[DatasetSummary]:
    """A paper's datasets in page order, or every dataset, most recently changed first."""
    query = _summaries_query()
    if paper_id is not None:
        await get_paper(session, paper_id)
        query = query.where(Dataset.paper_id == paper_id).order_by(Dataset.page, Dataset.created_at)
    else:
        query = query.order_by(Dataset.updated_at.desc(), Dataset.name)
    return [DatasetSummary(*row) for row in await session.execute(query)]


async def chart_uses(session: AsyncSession, dataset_id: uuid.UUID, column_ids: set[uuid.UUID]) -> list[ChartUse]:
    """Charts linked to the dataset, each with the dataset's columns its spec names. Read from the spec's ids, so this
    doesn't depend on the spec's shape."""
    charts = await session.execute(
        select(Chart.id, Chart.title, Chart.spec)
        .join(chart_datasets, chart_datasets.c.chart_id == Chart.id)
        .where(chart_datasets.c.dataset_id == dataset_id)
        .order_by(Chart.title)
    )
    uses = []
    for chart_id, title, spec in charts:
        named = {uuid.UUID(found) for found in _UUID.findall(str(spec))}
        uses.append(ChartUse(id=chart_id, title=title, column_ids=sorted(named & column_ids, key=str)))
    return uses


async def get_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> DatasetView:
    summary = (await session.execute(_summaries_query().where(Dataset.id == dataset_id))).one_or_none()
    if summary is None:
        raise NotFound(f"dataset {dataset_id} not found")
    columns = [
        ColumnView(c.id, c.position, c.name, c.unit)
        for c in await session.scalars(
            select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id).order_by(DatasetColumn.position)
        )
    ]
    rows = list(
        await session.scalars(
            select(DatasetRow).where(DatasetRow.dataset_id == dataset_id).order_by(DatasetRow.position)
        )
    )
    cells: dict[tuple[uuid.UUID, uuid.UUID], CellView] = {}
    row_ids = [r.id for r in rows]
    for c in await session.execute(select(cell_table).where(cell_table.c.row_id.in_(row_ids))):
        cells[(c.row_id, c.column_id)] = CellView(
            c.column_id, c.raw, c.value, c.error, c.origin, c.original_raw, c.page, c.bbox
        )
    empty = [CellView(col.id, "", None, None, "human", None, None, None) for col in columns]
    row_views = [
        RowView(r.id, r.position, [cells.get((r.id, col.id), empty[i]) for i, col in enumerate(columns)]) for r in rows
    ]
    charts = await chart_uses(session, dataset_id, {c.id for c in columns})
    return DatasetView(*summary, columns=columns, rows=row_views, charts=charts)


def _check_shape(grid: GridIn) -> None:
    if not 1 <= len(grid.columns) <= MAX_COLUMNS:
        raise InvalidInput(f"a dataset needs 1 to {MAX_COLUMNS} columns")
    if len(grid.rows) > MAX_ROWS:
        raise InvalidInput(f"a dataset can have at most {MAX_ROWS} rows")
    for number, row in enumerate(grid.rows, start=1):
        if len(row.cells) != len(grid.columns):
            raise InvalidInput(f"row {number} has {len(row.cells)} cells, expected {len(grid.columns)}")


def _cell_values(cell: CellIn, has_paper: bool) -> dict:
    if not has_paper and (cell.extracted is not None or cell.page is not None or cell.bbox is not None):
        raise InvalidInput("only a dataset from a paper can have cells read from a page")
    parsed = parse_number(cell.raw)
    extracted = cell.extracted is not None
    return {
        "raw": cell.raw,
        "value": parsed.value,
        "error": parsed.error,
        "origin": "extracted" if extracted else "human",
        "original_raw": cell.extracted if extracted and cell.raw != cell.extracted else None,
        "page": cell.page,
        "bbox": None if cell.bbox is None else [list(rect) for rect in cell.bbox],
    }


async def _write_grid(session: AsyncSession, dataset: Dataset, grid: GridIn) -> None:
    """Upserts rows and columns by id (positions follow the grid's order), deletes the ones not sent, and replaces
    every cell. The caller commits."""
    _check_shape(grid)
    has_paper = dataset.kind in ("table", "numbers")
    for table, items in ((DatasetColumn, grid.columns), (DatasetRow, grid.rows)):
        existing = set(await session.scalars(select(table.id).where(table.dataset_id == dataset.id)))
        sent = [item.id for item in items if item.id is not None]
        if len(sent) != len(set(sent)) or not set(sent) <= existing:
            raise InvalidInput(f"a {table.__tablename__.removeprefix('dataset_')[:-1]} id is not in this dataset")
        if gone := existing - set(sent):
            await session.execute(delete(table).where(table.id.in_(gone)))

    column_ids = await _upsert(session, DatasetColumn, dataset.id, grid.columns, _column_fields)
    row_ids = await _upsert(session, DatasetRow, dataset.id, grid.rows, _row_fields)
    await session.execute(delete(cell_table).where(cell_table.c.row_id.in_(row_ids)))
    cells = [
        {"row_id": row_id, "column_id": column_id, **_cell_values(cell, has_paper)}
        for row_id, row in zip(row_ids, grid.rows, strict=True)
        for column_id, cell in zip(column_ids, row.cells, strict=True)
    ]
    if cells:
        await session.execute(insert(cell_table), cells)
    await session.execute(update(Dataset).where(Dataset.id == dataset.id).values(updated_at=func.now()))


def _column_fields(column: ColumnIn) -> dict:
    return {"name": column.name, "unit": column.unit}


def _row_fields(_: RowIn) -> dict:
    return {}


async def _upsert(session: AsyncSession, table, dataset_id: uuid.UUID, items, fields) -> list[uuid.UUID]:
    """Ids in grid order: existing items are updated in place, new ones inserted."""
    updates = [{"id": item.id, "position": i, **fields(item)} for i, item in enumerate(items) if item.id is not None]
    if updates:
        await session.execute(update(table), updates)
    new = [{"dataset_id": dataset_id, "position": i, **fields(item)} for i, item in enumerate(items) if item.id is None]
    created = iter(
        await session.scalars(insert(table).returning(table.id, sort_by_parameter_order=True), new) if new else []
    )
    return [item.id if item.id is not None else next(created) for item in items]


async def create_dataset(
    session: AsyncSession,
    name: str,
    kind: str,
    grid: GridIn,
    *,
    paper_id: uuid.UUID | None = None,
    page: int | None = None,
    region: Rect | None = None,
) -> DatasetView:
    """A captured `table` (from a paper page and the region drawn on it) or the owner's own `user` data. The `numbers`
    dataset is only ever created by capturing a number."""
    if kind == "numbers":
        raise InvalidInput("a numbers dataset is created by capturing a number from a paper")
    if kind == "table":
        if paper_id is None or page is None or region is None:
            raise InvalidInput("a captured table needs its paper, page and region")
        paper = await get_paper(session, paper_id)
        if paper.page_count is not None and not 1 <= page <= paper.page_count:
            raise InvalidInput(f"page {page} is outside 1..{paper.page_count}")
        if not (region[0] < region[2] and region[1] < region[3]):
            raise InvalidInput("a region needs x0 < x1 and y0 < y1")
    elif kind == "user":
        if paper_id is not None or page is not None or region is not None:
            raise InvalidInput("own data has no paper, page or region")
    else:
        raise InvalidInput(f"unknown dataset kind {kind!r}")
    if any(item.id is not None for item in [*grid.columns, *grid.rows]):
        raise InvalidInput("a new dataset's rows and columns have no ids yet")

    dataset = Dataset(
        name=clean_name(name),
        kind=kind,
        paper_id=paper_id,
        page=page,
        region=None if region is None else list(region),
        extractor=TABLE_EXTRACTOR if kind == "table" else None,
    )
    session.add(dataset)
    await session.flush()
    await _write_grid(session, dataset, grid)
    await session.commit()
    return await get_dataset(session, dataset.id)


async def save_grid(session: AsyncSession, dataset_id: uuid.UUID, grid: GridIn, *, force: bool = False) -> DatasetView:
    """Replaces the dataset's grid. Removing a column a chart names needs `force`: the chart then reports that data as
    missing."""
    dataset = await _get(session, dataset_id)
    existing = set(await session.scalars(select(DatasetColumn.id).where(DatasetColumn.dataset_id == dataset_id)))
    removed = existing - {c.id for c in grid.columns if c.id is not None}
    if not force and any(set(use.column_ids) & removed for use in await chart_uses(session, dataset_id, existing)):
        raise Conflict("used_by_charts")
    await _write_grid(session, dataset, grid)
    await session.commit()
    return await get_dataset(session, dataset_id)


async def rename_dataset(session: AsyncSession, dataset_id: uuid.UUID, name: str) -> DatasetView:
    await _get(session, dataset_id)
    await session.execute(
        update(Dataset).where(Dataset.id == dataset_id).values(name=clean_name(name), updated_at=func.now())
    )
    await session.commit()
    return await get_dataset(session, dataset_id)


async def delete_dataset(session: AsyncSession, dataset_id: uuid.UUID, *, force: bool = False) -> None:
    """Deleting data a chart uses needs `force`; the chart stays and reports that data as missing."""
    await _get(session, dataset_id)
    used = await session.scalar(select(func.count()).where(chart_datasets.c.dataset_id == dataset_id))
    if used and not force:
        raise Conflict("used_by_charts")
    await session.execute(delete(Dataset).where(Dataset.id == dataset_id))
    await session.commit()
