"""What the datasets and charts tables promise on their own: allowed values, cascades, and what survives a delete."""

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Chart,
    Dataset,
    DatasetColumn,
    DatasetRow,
    Note,
    Paper,
    Provenance,
    cell_table,
    chart_datasets,
    note_charts,
)

pytestmark = pytest.mark.anyio


async def make_paper(session) -> Paper:
    paper = Paper(title="schema paper", file_path="/nonexistent.pdf", page_count=3)
    session.add(paper)
    await session.flush()
    return paper


async def make_table(session, paper: Paper | None) -> tuple[Dataset, DatasetColumn, DatasetRow]:
    dataset = Dataset(
        name="Table 1",
        kind="table" if paper else "user",
        paper_id=paper.id if paper else None,
        page=2 if paper else None,
        region=[72, 100, 300, 200] if paper else None,
    )
    session.add(dataset)
    await session.flush()
    column = DatasetColumn(dataset_id=dataset.id, position=0, name="F1")
    row = DatasetRow(dataset_id=dataset.id, position=0)
    session.add_all([column, row])
    await session.flush()
    await session.execute(
        insert(cell_table).values(
            row_id=row.id, column_id=column.id, raw="88.5", value=88.5, origin="extracted", page=2, bbox=[[1, 2, 3, 4]]
        )
    )
    return dataset, column, row


async def count(session, table) -> int:
    return await session.scalar(select(func.count()).select_from(table))


async def test_deleting_a_paper_keeps_its_datasets_and_their_cells(session):
    paper = await make_paper(session)
    dataset, _, _ = await make_table(session, paper)
    before = await count(session, cell_table)

    await session.execute(delete(Paper).where(Paper.id == paper.id))
    await session.refresh(dataset)

    assert dataset.paper_id is None
    assert await count(session, cell_table) == before


async def test_deleting_a_dataset_removes_its_columns_rows_cells_and_chart_links(session):
    dataset, column, row = await make_table(session, await make_paper(session))
    chart = Chart(title="F1", spec={"version": 1}, spec_version=1)
    session.add(chart)
    await session.flush()
    await session.execute(insert(chart_datasets).values(chart_id=chart.id, dataset_id=dataset.id))

    await session.execute(delete(Dataset).where(Dataset.id == dataset.id))

    # Counted with queries: session.get would return the objects still held in the session's identity map.
    assert await session.scalar(select(func.count()).where(DatasetColumn.id == column.id)) == 0
    assert await session.scalar(select(func.count()).where(DatasetRow.id == row.id)) == 0
    assert await session.scalar(select(func.count()).where(cell_table.c.row_id == row.id)) == 0
    assert await session.scalar(select(func.count()).where(chart_datasets.c.chart_id == chart.id)) == 0
    assert await session.get(Chart, chart.id) is not None  # the chart stays; its data is reported missing


async def test_deleting_a_chart_or_a_note_removes_only_the_embed(session):
    note = Note(body="see chart", provenance=Provenance.HUMAN)
    kept_chart = Chart(title="kept", spec={"version": 1}, spec_version=1)
    gone_chart = Chart(title="gone", spec={"version": 1}, spec_version=1)
    session.add_all([note, kept_chart, gone_chart])
    await session.flush()
    links = [{"note_id": note.id, "chart_id": kept_chart.id}, {"note_id": note.id, "chart_id": gone_chart.id}]
    await session.execute(insert(note_charts), links)

    await session.execute(delete(Chart).where(Chart.id == gone_chart.id))
    assert await session.get(Note, note.id) is not None
    assert await session.scalar(select(func.count()).where(note_charts.c.note_id == note.id)) == 1

    await session.execute(delete(Note).where(Note.id == note.id))
    assert await session.get(Chart, kept_chart.id) is not None
    assert await session.scalar(select(func.count()).where(note_charts.c.chart_id == kept_chart.id)) == 0


@pytest.mark.parametrize(
    ("column", "value"),
    [("kind", "figure"), ("origin", "llm")],
)
async def test_kind_and_origin_only_take_known_values(session, column, value):
    dataset, column_row, row = await make_table(session, None)
    await session.commit()
    with pytest.raises(IntegrityError):
        if column == "kind":
            session.add(Dataset(name="bad", kind=value))
            await session.flush()
        else:
            await session.execute(
                insert(cell_table).values(row_id=row.id, column_id=column_row.id, raw="x", origin=value)
            )
    await session.rollback()


async def test_a_paper_has_at_most_one_numbers_dataset(session):
    paper = await make_paper(session)
    session.add(Dataset(name="Numbers", kind="numbers", paper_id=paper.id))
    await session.commit()
    with pytest.raises(IntegrityError):
        session.add(Dataset(name="Numbers again", kind="numbers", paper_id=paper.id))
        await session.flush()
    await session.rollback()


async def test_names_and_titles_cannot_be_blank(session):
    with pytest.raises(IntegrityError):
        session.add(Dataset(name="   ", kind="user"))
        await session.flush()
    await session.rollback()
    with pytest.raises(IntegrityError):
        session.add(Chart(title="", spec={"version": 1}, spec_version=1))
        await session.flush()
    await session.rollback()
