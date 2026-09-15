import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.chart_spec import ChartSpec
from app.schemas.papers import Rect

ChartType = Literal["bar", "line", "scatter", "box", "scatter3d", "heatmap", "surface", "contour", "parcoords"]


class ChartCreate(BaseModel):
    title: str  # stripped and checked (1..200 characters) by core/charts.py, which answers 422
    spec: ChartSpec


class ChartUpdate(BaseModel):
    """A rename, a new spec, or both."""

    title: str | None = None
    spec: ChartSpec | None = None

    @model_validator(mode="after")
    def has_a_change(self) -> Self:
        if self.title is None and self.spec is None:
            raise ValueError("send a title, a spec, or both")
        return self


class ChartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    spec: ChartSpec
    spec_version: int
    note_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class ChartSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    type: ChartType
    sources: list[str]
    note_count: int
    updated_at: datetime


class ResolveRequest(BaseModel):
    spec: ChartSpec


class ResolvedCellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw: str
    value: float | None
    error: float | None
    origin: Literal["extracted", "human"]
    original_raw: str | None
    page: int | None
    bbox: list[Rect] | None


class ResolvedColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str | None


class ResolvedRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    cells: dict[uuid.UUID, ResolvedCellOut]  # keyed by column id: only the columns the spec names


class ResolvedDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Literal["table", "numbers", "user"]
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    region: Rect | None
    columns: list[ResolvedColumnOut]
    rows: list[ResolvedRowOut]


class MissingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal["dataset", "column", "row"]
    id: uuid.UUID


class ResolvedDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    datasets: list[ResolvedDatasetOut]
    missing: list[MissingOut]
