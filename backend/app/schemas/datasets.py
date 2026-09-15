import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core import datasets
from app.schemas.papers import Rect

# Limits a request can't exceed; core/datasets.py checks the same row and column limits for every caller.
CELL_CHARS = 2_000
MAX_CELL_RECTS = 50


class CellIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw: str = Field(default="", max_length=CELL_CHARS)
    # What extraction read, for a cell that came from the PDF; send it back unchanged when saving a grid.
    extracted: str | None = Field(default=None, max_length=CELL_CHARS)
    page: int | None = Field(default=None, ge=1)
    bbox: list[Rect] | None = Field(default=None, min_length=1, max_length=MAX_CELL_RECTS)


class ColumnIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    name: str = Field(default="", max_length=datasets.NAME_MAX_CHARS)
    unit: str | None = Field(default=None, max_length=40)


class RowIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    cells: list[CellIn] = Field(max_length=datasets.MAX_COLUMNS)


class GridIn(BaseModel):
    """A whole grid. Existing rows and columns carry their ids; new ones have none."""

    model_config = ConfigDict(from_attributes=True)

    columns: list[ColumnIn] = Field(max_length=datasets.MAX_COLUMNS)
    rows: list[RowIn] = Field(max_length=datasets.MAX_ROWS)

    def to_core(self) -> datasets.GridIn:
        return datasets.GridIn(
            columns=[datasets.ColumnIn(id=c.id, name=c.name, unit=c.unit) for c in self.columns],
            rows=[
                datasets.RowIn(
                    id=r.id,
                    cells=[
                        datasets.CellIn(raw=c.raw, extracted=c.extracted, page=c.page, bbox=c.bbox) for c in r.cells
                    ],
                )
                for r in self.rows
            ],
        )


class DatasetCreate(BaseModel):
    name: str  # stripped and checked (1..200 characters) by core/datasets.py, which answers 422
    kind: Literal["table", "user"]
    paper_id: uuid.UUID | None = None
    page: int | None = Field(default=None, ge=1)
    region: Rect | None = None
    grid: GridIn


class DatasetRename(BaseModel):
    name: str


class CellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    column_id: uuid.UUID
    raw: str
    value: float | None
    error: float | None
    origin: Literal["extracted", "human"]
    original_raw: str | None
    page: int | None
    bbox: list[Rect] | None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    name: str
    unit: str | None


class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    cells: list[CellOut]


class ChartUseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    column_ids: list[uuid.UUID]


class DatasetSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Literal["table", "numbers", "user"]
    paper_id: uuid.UUID | None
    paper_title: str | None
    page: int | None
    region: Rect | None
    row_count: int
    column_count: int
    created_at: datetime
    updated_at: datetime


class DatasetOut(DatasetSummaryOut):
    columns: list[ColumnOut]
    rows: list[RowOut]
    charts: list[ChartUseOut]


class TablePreviewRequest(BaseModel):
    page: int = Field(ge=1)
    region: Rect


class TablePreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    grid: GridIn


class NumberCreate(BaseModel):
    label: str
    raw: str = Field(max_length=200)
    unit: str = ""
    page: int = Field(ge=1)
    bbox: list[Rect] = Field(min_length=1, max_length=MAX_CELL_RECTS)


class NumberAddedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: uuid.UUID
    row_id: uuid.UUID


class NumberCandidatesRequest(BaseModel):
    text: str = Field(max_length=5_000)


class NumberCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw: str
    value: float
    error: float | None
    unit_hint: str | None
