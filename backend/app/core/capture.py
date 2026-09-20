"""Getting numbers in: a table from a box drawn on a page, one number selected in the text, or the owner's own CSV."""

import asyncio
import csv
import io
import uuid
from dataclasses import dataclass

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import datasets
from app.core.datasets import CellIn, ColumnIn, DatasetView, GridIn, Rect, RowIn, clean_name
from app.core.errors import InvalidInput
from app.core.numbers import parse_number
from app.core.papers import get_paper, get_paper_file
from app.core.table_grid import caption_name, split_header, words_to_grid
from app.models import Dataset, DatasetColumn, DatasetRow, Paper, cell_table
from app.providers.extraction import read_region

UNIT_MAX_CHARS = 40
MAX_IMPORT_BYTES = 2_000_000
NUMBER_COLUMNS = ("Label", "Value", "Unit")
IMPORTED_NAME = "Imported data"


@dataclass(frozen=True)
class TablePreview:
    name: str | None  # the table's caption, when one sits next to the box
    grid: GridIn  # rows and columns without ids; every cell with text is marked as read from the page


@dataclass(frozen=True)
class NumberAdded:
    dataset_id: uuid.UUID
    row_id: uuid.UUID


def _check_page(paper: Paper, page: int) -> None:
    if page < 1 or (paper.page_count is not None and page > paper.page_count):
        raise InvalidInput(f"page {page} is outside 1..{paper.page_count}")


async def preview_table(session: AsyncSession, paper_id: uuid.UUID, page: int, region: Rect) -> TablePreview:
    """The proposed grid for a box drawn on a page, the table's own header row read as the column names (so a chart
    built on it can label its axes). Nothing is saved: the owner fixes the grid, then creates the dataset with it."""
    paper = await get_paper(session, paper_id)
    _check_page(paper, page)
    if not (region[0] < region[2] and region[1] < region[3]):
        raise InvalidInput("a region needs x0 < x1 and y0 < y1")
    path = await get_paper_file(session, paper_id)
    text = await asyncio.to_thread(read_region, path, page, region)
    names, body = split_header(words_to_grid(text.words))
    grid = GridIn(
        columns=[ColumnIn(id=None, name=name, unit=None) for name in names],
        rows=[
            RowIn(
                id=None,
                cells=[
                    CellIn(raw=cell.text, extracted=cell.text, page=page, bbox=[cell.bbox]) if cell.bbox else CellIn("")
                    for cell in row
                ],
            )
            for row in body
        ],
    )
    return TablePreview(name=caption_name(text.blocks, region) if names else None, grid=grid)


async def _number_columns(session: AsyncSession, dataset: Dataset) -> dict[str, uuid.UUID]:
    """The Label, Value and Unit columns by name. ponytail: the owner can rename, reorder or delete them in the grid
    editor; a missing one is added back at the end rather than guessing which renamed column it became."""
    query = select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id).order_by(DatasetColumn.position)
    columns = list(await session.scalars(query))
    by_name = {c.name: c.id for c in columns}
    position = len(columns)
    for name in NUMBER_COLUMNS:
        if name not in by_name:
            column = DatasetColumn(dataset_id=dataset.id, position=position, name=name)
            session.add(column)
            await session.flush()
            by_name[name] = column.id
            position += 1
    return by_name


async def add_number(
    session: AsyncSession, paper_id: uuid.UUID, label: str, raw: str, unit: str, page: int, bbox: list[Rect]
) -> NumberAdded:
    """Appends a row (label, value, unit) to the paper's numbers dataset, creating it on first use. The value cell is
    anchored on the selected text."""
    paper = await get_paper(session, paper_id)
    _check_page(paper, page)
    if not bbox:
        raise InvalidInput("a captured number needs the rects of its selection")
    label = clean_name(label)
    unit = unit.strip()
    if len(unit) > UNIT_MAX_CHARS:
        raise InvalidInput(f"a unit has at most {UNIT_MAX_CHARS} characters")
    parsed = parse_number(raw)
    if parsed.value is None:
        raise InvalidInput(f"{raw.strip()!r} is not a number")

    # ponytail: check-then-insert; two captures racing on a paper's first number hit the unique index. Single user.
    dataset = await session.scalar(select(Dataset).where(Dataset.paper_id == paper_id, Dataset.kind == "numbers"))
    if dataset is None:
        dataset = Dataset(name=clean_name(f"Numbers from {paper.title}"[: datasets.NAME_MAX_CHARS]), kind="numbers",
                          paper_id=paper_id)  # fmt: skip
        session.add(dataset)
        await session.flush()
    columns = await _number_columns(session, dataset)
    position = await session.scalar(select(func.count()).where(DatasetRow.dataset_id == dataset.id))
    row = DatasetRow(dataset_id=dataset.id, position=position)
    session.add(row)
    await session.flush()
    typed = {"value": None, "error": None, "origin": "human", "page": None, "bbox": None}
    # Every row has every key: an executemany insert takes its columns from the first row.
    await session.execute(
        insert(cell_table),
        [
            {"row_id": row.id, "column_id": columns["Label"], "raw": label, **typed},
            {"row_id": row.id, "column_id": columns["Value"], "raw": raw.strip(), "value": parsed.value,
             "error": parsed.error, "origin": "extracted", "page": page, "bbox": [list(rect) for rect in bbox]},
            {"row_id": row.id, "column_id": columns["Unit"], "raw": unit, **typed},
        ],
    )  # fmt: skip
    await session.execute(update(Dataset).where(Dataset.id == dataset.id).values(updated_at=func.now()))
    await session.commit()
    return NumberAdded(dataset_id=dataset.id, row_id=row.id)


async def import_csv(session: AsyncSession, name: str | None, data: bytes) -> DatasetView:
    """Own data from CSV text: a file, or text pasted from a spreadsheet (tabs). The first row names the columns."""
    if len(data) > MAX_IMPORT_BYTES:
        raise InvalidInput(f"the file is too large (over {MAX_IMPORT_BYTES // 1_000_000} MB)")
    not_utf8 = "the file isn't UTF-8 text; save it as UTF-8 CSV and try again"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidInput(not_utf8) from None
    # NUL decodes as UTF-8 (UTF-16 without a byte-order mark is full of it), but Postgres text can't store it.
    if "\x00" in text:
        raise InvalidInput(not_utf8)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    except csv.Error:  # one column: there's no delimiter to find
        dialect = csv.excel
    try:
        rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(value.strip() for value in row)]
    except csv.Error as error:  # e.g. a field over csv.field_size_limit()
        raise InvalidInput(f"the file isn't valid CSV: {error}") from None
    if not rows:
        raise InvalidInput("the file is empty")
    header, body = rows[0], rows[1:]
    for number, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise InvalidInput(f"row {number} has {len(row)} values, but the header has {len(header)}")
    grid = GridIn(
        columns=[ColumnIn(id=None, name=title.strip(), unit=None) for title in header],
        rows=[RowIn(id=None, cells=[CellIn(raw=value.strip()) for value in row]) for row in body],
    )
    return await datasets.create_dataset(session, name or IMPORTED_NAME, "user", grid)
