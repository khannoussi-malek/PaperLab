"""A captured table as it comes in, and the limits on its size."""

import uuid
from dataclasses import dataclass

Rect = tuple[float, float, float, float]
NAME_MAX_CHARS = 200
MAX_ROWS = 5_000
MAX_COLUMNS = 100


@dataclass(frozen=True)
class CellIn:
    raw: str
    # The text extraction read, for a cell that came from the PDF. None for a cell the owner typed.
    extracted: str | None = None
    page: int | None = None
    bbox: list[Rect] | None = None
    # What a model wrote, for a cell it suggested (D33): marked as the model's, and as edited once raw differs.
    suggested: str | None = None


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
