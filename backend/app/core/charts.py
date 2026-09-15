"""Charts: a title and a spec that names data by id. `resolve` fetches the current cells a spec names, so fixing a cell
fixes every chart; data that has since been deleted comes back as `missing` instead of failing the chart."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chart_spec import ChartSpec, references
from app.core.datasets import clean_name
from app.core.errors import InvalidInput, NotFound
from app.models import Chart, Dataset, DatasetColumn, DatasetRow, Paper, cell_table, chart_datasets, note_charts

COPY_SUFFIX = " (copy)"
OWN_DATA_LABEL = "My data"


@dataclass(frozen=True)
class ChartSummary:
    id: uuid.UUID
    title: str
    type: str
    sources: list[str]  # where the data comes from: paper titles, then "My data"
    note_count: int
    updated_at: datetime


@dataclass(frozen=True)
class ChartView:
    id: uuid.UUID
    title: str
    spec: dict
    spec_version: int
    note_ids: list[uuid.UUID]  # notes that show this chart
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ResolvedCell:
    raw: str
    value: float | None
    error: float | None
    origin: str
    original_raw: str | None
    page: int | None
    bbox: list[list[float]] | None


@dataclass(frozen=True)
class ResolvedColumn:
    id: uuid.UUID
    name: str
    unit: str | None


@dataclass(frozen=True)
class ResolvedRow:
    id: uuid.UUID
    position: int
    cells: dict[uuid.UUID, ResolvedCell]  # only the columns the spec names


@dataclass(frozen=True)
class ResolvedDataset:
    id: uuid.UUID
    name: str
    kind: str
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    columns: list[ResolvedColumn]
    rows: list[ResolvedRow]  # every row, in position order; a series' row filter is applied when drawing


@dataclass(frozen=True)
class Missing:
    kind: Literal["dataset", "column", "row"]
    id: uuid.UUID


@dataclass(frozen=True)
class ResolvedData:
    datasets: list[ResolvedDataset]
    missing: list[Missing]


async def resolve(session: AsyncSession, spec: ChartSpec) -> ResolvedData:
    refs = references(spec)
    found = {
        d.id: d
        for d in await session.execute(
            select(Dataset.id, Dataset.name, Dataset.kind, Dataset.paper_id, Paper.title.label("paper_title"),
                   Dataset.page)
            .outerjoin(Paper, Paper.id == Dataset.paper_id)
            .where(Dataset.id.in_(refs))
        )
    }  # fmt: skip
    missing = [Missing("dataset", dataset_id) for dataset_id in refs if dataset_id not in found]
    wanted_columns = {c for dataset_id, (columns, _) in refs.items() if dataset_id in found for c in columns}
    columns = list(
        await session.scalars(
            select(DatasetColumn).where(DatasetColumn.id.in_(wanted_columns)).order_by(DatasetColumn.position)
        )
    )
    rows = list(
        await session.scalars(
            select(DatasetRow).where(DatasetRow.dataset_id.in_(found)).order_by(DatasetRow.position)
        )
    )
    cells = await session.execute(
        select(cell_table).where(
            cell_table.c.column_id.in_([c.id for c in columns]), cell_table.c.row_id.in_([r.id for r in rows])
        )
    )
    by_row: dict[uuid.UUID, dict[uuid.UUID, ResolvedCell]] = {}
    for c in cells:
        by_row.setdefault(c.row_id, {})[c.column_id] = ResolvedCell(
            c.raw, c.value, c.error, c.origin, c.original_raw, c.page, c.bbox
        )

    resolved = []
    for dataset_id, (named_columns, named_rows) in refs.items():
        if dataset_id not in found:
            continue
        own_columns = [c for c in columns if c.dataset_id == dataset_id and c.id in named_columns]
        own_rows = [r for r in rows if r.dataset_id == dataset_id]
        # A column id that belongs to another dataset is missing for this one, like a deleted column.
        missing += [Missing("column", c) for c in named_columns - {c.id for c in own_columns}]
        missing += [Missing("row", r) for r in named_rows - {r.id for r in own_rows}]
        d = found[dataset_id]
        resolved.append(
            ResolvedDataset(
                id=d.id, name=d.name, kind=d.kind, paper_id=d.paper_id, paper_title=d.paper_title, page=d.page,
                columns=[ResolvedColumn(c.id, c.name, c.unit) for c in own_columns],
                rows=[ResolvedRow(r.id, r.position, by_row.get(r.id, {})) for r in own_rows],
            )
        )  # fmt: skip
    return ResolvedData(datasets=resolved, missing=missing)


async def _check_references(session: AsyncSession, spec: ChartSpec) -> None:
    missing = (await resolve(session, spec)).missing
    if missing:
        names = ", ".join(f"{m.kind} {m.id}" for m in missing[:3])
        raise InvalidInput(f"the chart names data that doesn't exist: {names}")


async def _link_datasets(session: AsyncSession, chart_id: uuid.UUID, spec: ChartSpec) -> None:
    await session.execute(delete(chart_datasets).where(chart_datasets.c.chart_id == chart_id))
    await session.execute(insert(chart_datasets), [{"chart_id": chart_id, "dataset_id": d} for d in references(spec)])


async def _get(session: AsyncSession, chart_id: uuid.UUID) -> Chart:
    chart = await session.get(Chart, chart_id)
    if chart is None:
        raise NotFound(f"chart {chart_id} not found")
    return chart


async def get_chart(session: AsyncSession, chart_id: uuid.UUID) -> ChartView:
    chart = await _get(session, chart_id)
    await session.refresh(chart)
    shown_in = select(note_charts.c.note_id).where(note_charts.c.chart_id == chart_id)
    note_ids = list(await session.scalars(shown_in))
    return ChartView(
        chart.id, chart.title, chart.spec, chart.spec_version, note_ids, chart.created_at, chart.updated_at
    )


async def list_charts(session: AsyncSession) -> list[ChartSummary]:
    """Every chart, most recently changed first."""
    note_count = select(func.count()).where(note_charts.c.chart_id == Chart.id).scalar_subquery()
    rows = await session.execute(
        select(Chart.id, Chart.title, Chart.spec["type"].astext, note_count, Chart.updated_at).order_by(
            Chart.updated_at.desc(), Chart.title
        )
    )
    sources: dict[uuid.UUID, list[str]] = {}
    linked = await session.execute(
        select(chart_datasets.c.chart_id, Dataset.kind, Dataset.name, Paper.title)
        .join(Dataset, Dataset.id == chart_datasets.c.dataset_id)
        .outerjoin(Paper, Paper.id == Dataset.paper_id)
        .order_by(Paper.title.nulls_last(), Dataset.name)
    )
    for chart_id, kind, name, paper_title in linked:
        label = paper_title or (OWN_DATA_LABEL if kind == "user" else name)
        labels = sources.setdefault(chart_id, [])
        if label not in labels:
            labels.append(label)
    return [
        ChartSummary(chart_id, title, kind, sources.get(chart_id, []), notes, updated)
        for chart_id, title, kind, notes, updated in rows
    ]


async def create_chart(session: AsyncSession, title: str, spec: ChartSpec) -> ChartView:
    title = clean_name(title)
    await _check_references(session, spec)
    chart = Chart(title=title, spec=spec.model_dump(mode="json"), spec_version=spec.version)
    session.add(chart)
    await session.flush()
    await _link_datasets(session, chart.id, spec)
    await session.commit()
    return await get_chart(session, chart.id)


async def update_chart(
    session: AsyncSession, chart_id: uuid.UUID, *, title: str | None = None, spec: ChartSpec | None = None
) -> ChartView:
    """Renames the chart, replaces its spec, or both. Notes that show it show the new version."""
    await _get(session, chart_id)
    values: dict = {"updated_at": func.now()}
    if title is not None:
        values["title"] = clean_name(title)
    if spec is not None:
        await _check_references(session, spec)
        values.update(spec=spec.model_dump(mode="json"), spec_version=spec.version)
        await _link_datasets(session, chart_id, spec)
    await session.execute(update(Chart).where(Chart.id == chart_id).values(**values))
    await session.commit()
    return await get_chart(session, chart_id)


async def duplicate_chart(session: AsyncSession, chart_id: uuid.UUID) -> ChartView:
    """A new chart with the same spec, reading the same datasets. Not shown in any note."""
    original = await _get(session, chart_id)
    title = original.title[: 200 - len(COPY_SUFFIX)] + COPY_SUFFIX
    copy = Chart(title=title, spec=original.spec, spec_version=original.spec_version)
    session.add(copy)
    await session.flush()
    linked = select(chart_datasets.c.dataset_id).where(chart_datasets.c.chart_id == chart_id)
    links = [{"chart_id": copy.id, "dataset_id": d} for d in await session.scalars(linked)]
    if links:
        await session.execute(insert(chart_datasets), links)
    await session.commit()
    return await get_chart(session, copy.id)


async def delete_chart(session: AsyncSession, chart_id: uuid.UUID) -> None:
    """Notes that showed the chart stay; they just no longer show it."""
    await _get(session, chart_id)
    await session.execute(delete(Chart).where(Chart.id == chart_id))
    await session.commit()
