"""Table capture accuracy: the share of cells the proposed grid gets right before the owner fixes anything.

    docker compose exec api python -m evals.words_grid
    cd backend && uv run python -m evals.words_grid --database-url postgresql+asyncpg://paperlab:paperlab@localhost:5433/paperlab

Each table in evals/tables.yaml names a paper by its exact title, a page, the box a person would draw, and the grid a
careful reader types from the PDF. The box is read with the code the "Capture table" preview uses. A cell is right when
its text matches after collapsing whitespace; a missing or extra row or column makes its cells wrong. Exits 2 on a
malformed tables file or a paper title that matches no paper or several.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core.table_grid import words_to_grid
from app.models import Paper
from app.providers.extraction import read_region

TABLES = Path(__file__).with_name("tables.yaml")


class Table(BaseModel):
    paper: str
    label: str  # e.g. "Table 3", for the report
    page: int = Field(ge=1)
    region: tuple[float, float, float, float]
    rows: list[list[str]] = Field(min_length=1)


def _text(value: str) -> str:
    return " ".join(value.split())


def cell_accuracy(proposed: list[list[str]], truth: list[list[str]]) -> tuple[int, int]:
    """(right, total). Total covers the larger of the two grids, so a shape mismatch costs every cell it shifts."""
    rows = max(len(proposed), len(truth))
    columns = max((len(row) for row in [*proposed, *truth]), default=0)
    right = sum(
        1
        for r in range(min(len(proposed), len(truth)))
        for c in range(min(len(proposed[r]), len(truth[r])))
        if _text(proposed[r][c]) == _text(truth[r][c])
    )
    return right, rows * columns


def measure(path: str | Path, table: Table) -> tuple[int, int]:
    grid = words_to_grid(read_region(path, table.page, table.region).words)
    return cell_accuracy([[cell.text for cell in row] for row in grid], table.rows)


def load_tables(path: Path = TABLES) -> list[Table]:
    return [Table.model_validate(entry) for entry in yaml.safe_load(path.read_text()) or []]


async def _paper_files(database_url: str, titles: set[str]) -> dict[str, str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(select(Paper.title, Paper.file_path).where(Paper.title.in_(titles)))).all()
    finally:
        await engine.dispose()
    files: dict[str, list[str]] = {}
    for title, file_path in rows:
        files.setdefault(title, []).append(file_path)
    bad = sorted(t for t in titles if len(files.get(t, [])) != 1)
    if bad:
        raise LookupError(f"each title must match exactly one paper: {bad}")
    return {title: paths[0] for title, paths in files.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args(argv)
    try:
        tables = load_tables()
        files = asyncio.run(_paper_files(args.database_url, {t.paper for t in tables}))
    except (ValidationError, LookupError, yaml.YAMLError) as error:
        print(error, file=sys.stderr)
        return 2
    total_right = total_cells = 0
    for table in tables:
        right, cells = measure(files[table.paper], table)
        total_right, total_cells = total_right + right, total_cells + cells
        print(f"{table.paper[:40]:40}  {table.label:9}  {right:4}/{cells:<4}  {right / cells:6.1%}")
    print(f"{'all tables':40}  {'':9}  {total_right:4}/{total_cells:<4}  {total_right / max(total_cells, 1):6.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
