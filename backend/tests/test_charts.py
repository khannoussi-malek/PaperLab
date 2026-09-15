import uuid

import pytest
from sqlalchemy import event, insert

from app.core import charts, datasets
from app.core.chart_spec import ChartSpecAdapter
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.errors import InvalidInput, NotFound
from app.models import Note, Paper, Provenance, note_charts

pytestmark = pytest.mark.anyio


def grid(names: tuple[str, ...], *rows: tuple[str, ...], page: int | None = None) -> GridIn:
    def cell(text: str) -> CellIn:
        return CellIn(raw=text, extracted=text, page=page, bbox=[(72.0, 100.0, 90.0, 110.0)]) if page else CellIn(text)

    return GridIn(
        columns=[ColumnIn(id=None, name=n, unit=None) for n in names],
        rows=[RowIn(id=None, cells=[cell(t) for t in row]) for row in rows],
    )


async def bert_table(session) -> datasets.DatasetView:
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", page_count=9)
    session.add(paper)
    await session.commit()
    return await datasets.create_dataset(
        session, "Table 2", "table", grid(("System", "F1"), ("BERT-B", "88.5 ± 0.3"), ("BERT-L", "90.9"), page=7),
        paper_id=paper.id, page=7, region=(70, 60, 290, 240),
    )  # fmt: skip


async def my_runs(session) -> datasets.DatasetView:
    return await datasets.create_dataset(session, "My runs", "user", grid(("Run", "F1"), ("mine", "92.0")))


def bar(*sources: datasets.DatasetView, **series_fields):
    return ChartSpecAdapter.validate_python({
        "type": "bar",
        "series": [
            {"id": f"s{i}", "dataset_id": str(d.id), "x": str(d.columns[0].id), "y": str(d.columns[1].id),
             **series_fields}
            for i, d in enumerate(sources)
        ],
    })  # fmt: skip


async def test_a_chart_links_its_datasets_and_lists_where_its_data_comes_from(session):
    bert, mine = await bert_table(session), await my_runs(session)

    chart = await charts.create_chart(session, "  SQuAD F1 ", bar(bert, mine))

    assert (chart.title, chart.spec_version, chart.note_ids) == ("SQuAD F1", 1, [])
    assert chart.spec == bar(bert, mine).model_dump(mode="json")
    assert await charts.get_chart(session, chart.id) == chart
    summary = next(c for c in await charts.list_charts(session) if c.id == chart.id)
    assert (summary.title, summary.type, summary.note_count) == ("SQuAD F1", "bar", 0)
    assert summary.sources == ["BERT", "My data"]
    assert [use.id for use in (await datasets.get_dataset(session, bert.id)).charts] == [chart.id]


async def test_resolve_returns_only_the_named_columns_of_every_row_with_their_sources(session):
    bert = await bert_table(session)
    system, f1 = bert.columns

    data = await charts.resolve(session, bar(bert))

    assert data.missing == []
    [resolved] = data.datasets
    assert (resolved.id, resolved.name, resolved.kind) == (bert.id, "Table 2", "table")
    assert (resolved.paper_title, resolved.page) == ("BERT", 7)
    assert [(c.id, c.name) for c in resolved.columns] == [(system.id, "System"), (f1.id, "F1")]
    first = resolved.rows[0]
    assert (first.id, first.position) == (bert.rows[0].id, 0)
    cell = first.cells[f1.id]
    assert (cell.raw, cell.value, cell.error, cell.origin, cell.page, cell.bbox) == (
        "88.5 ± 0.3", 88.5, 0.3, "extracted", 7, [[72, 100, 90, 110]]
    )


async def test_fixing_a_cell_changes_what_every_chart_using_it_resolves(session):
    bert = await bert_table(session)
    spec = bar(bert)
    await charts.create_chart(session, "F1", spec)
    fixed = GridIn(
        columns=[ColumnIn(c.id, c.name, c.unit) for c in bert.columns],
        rows=[RowIn(r.id, [CellIn(raw="BERT-B", extracted="BERT-B", page=7),
                           CellIn(raw="89.1", extracted="88.5 ± 0.3", page=7)])
              if i == 0 else RowIn(r.id, [CellIn(raw=c.raw) for c in r.cells]) for i, r in enumerate(bert.rows)],
    )  # fmt: skip
    await datasets.save_grid(session, bert.id, fixed)

    resolved = (await charts.resolve(session, spec)).datasets[0]

    assert resolved.rows[0].cells[bert.columns[1].id].value == 89.1


async def test_resolve_reads_cells_with_as_many_parameters_however_many_rows_a_dataset_has(session):
    # asyncpg takes at most 32,767 bind parameters: one per row would fail on large datasets.
    def runs(row_count: int):
        return grid(("Run", "F1"), *[(f"run {i}", str(i)) for i in range(row_count)])

    small = await datasets.create_dataset(session, "Small", "user", runs(2))
    large = await datasets.create_dataset(session, "Large", "user", runs(60))
    seen: list[int] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "FROM cells" in statement:
            seen.append(len(parameters))

    sync_engine = session.bind.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        for source in (small, large):
            [resolved] = (await charts.resolve(session, bar(source))).datasets
            assert len(resolved.rows) == len(source.rows)
            assert all(len(row.cells) == 2 for row in resolved.rows)
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)

    assert len(seen) == 2
    assert seen[0] == seen[1]


async def test_resolve_reports_data_that_is_gone_and_draws_the_rest(session):
    bert, mine = await bert_table(session), await my_runs(session)
    stray_row = uuid.uuid4()

    # A row id that isn't in the dataset, and a column that exists but belongs to another dataset.
    spec = ChartSpecAdapter.validate_python({"type": "bar", "series": [
        {"id": "a", "dataset_id": str(bert.id), "y": str(bert.columns[1].id),
         "rows": [str(bert.rows[0].id), str(stray_row)]},
        {"id": "b", "dataset_id": str(bert.id), "y": str(mine.columns[1].id)},
    ]})  # fmt: skip
    partly = await charts.resolve(session, spec)

    assert [d.id for d in partly.datasets] == [bert.id]
    assert {(m.kind, m.id) for m in partly.missing} == {("row", stray_row), ("column", mine.columns[1].id)}
    assert [c.id for c in partly.datasets[0].columns] == [bert.columns[1].id]

    await datasets.delete_dataset(session, mine.id)
    gone = await charts.resolve(session, bar(bert, mine))
    assert [d.id for d in gone.datasets] == [bert.id]
    assert [(m.kind, m.id) for m in gone.missing] == [("dataset", mine.id)]


async def test_a_chart_cannot_be_saved_naming_data_that_does_not_exist(session):
    bert = await bert_table(session)
    spec = bar(bert)
    broken = ChartSpecAdapter.validate_python({
        "type": "scatter", "series": [{"id": "s", "dataset_id": str(bert.id), "y": str(uuid.uuid4())}],
    })  # fmt: skip

    with pytest.raises(InvalidInput, match="doesn't exist"):
        await charts.create_chart(session, "F1", broken)
    chart = await charts.create_chart(session, "F1", spec)
    with pytest.raises(InvalidInput, match="doesn't exist"):
        await charts.update_chart(session, chart.id, spec=broken)
    with pytest.raises(InvalidInput):
        await charts.create_chart(session, " ", spec)


async def test_editing_a_chart_renames_it_and_relinks_its_datasets(session):
    bert, mine = await bert_table(session), await my_runs(session)
    chart = await charts.create_chart(session, "F1", bar(bert, mine))

    renamed = await charts.update_chart(session, chart.id, title="Dev F1")
    assert (renamed.title, renamed.spec) == ("Dev F1", chart.spec)
    edited = await charts.update_chart(session, chart.id, spec=bar(mine))

    assert edited.spec == bar(mine).model_dump(mode="json")
    assert (await datasets.get_dataset(session, bert.id)).charts == []
    assert [u.id for u in (await datasets.get_dataset(session, mine.id)).charts] == [chart.id]
    with pytest.raises(InvalidInput):
        await charts.update_chart(session, chart.id, title="  ")
    with pytest.raises(NotFound):
        await charts.update_chart(session, uuid.uuid4(), title="x")


async def test_a_duplicate_is_an_independent_chart_on_the_same_data(session):
    bert = await bert_table(session)
    original = await charts.create_chart(session, "SQuAD F1", bar(bert))
    note = Note(body="see chart", provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    await session.execute(insert(note_charts).values(note_id=note.id, chart_id=original.id))
    await session.commit()

    copy = await charts.duplicate_chart(session, original.id)

    assert copy.id != original.id
    assert (copy.title, copy.spec, copy.note_ids) == ("SQuAD F1 (copy)", original.spec, [])
    assert {u.id for u in (await datasets.get_dataset(session, bert.id)).charts} == {original.id, copy.id}
    await charts.update_chart(session, copy.id, spec=bar(bert, trend="none"), title="Mine now")
    line = ChartSpecAdapter.validate_python({**copy.spec, "type": "line"})
    await charts.update_chart(session, copy.id, spec=line)
    assert (await charts.get_chart(session, original.id)).spec["type"] == "bar"
    assert (await charts.get_chart(session, original.id)).note_ids == [note.id]

    long = await charts.create_chart(session, "x" * 200, bar(bert))
    assert (await charts.duplicate_chart(session, long.id)).title == "x" * 193 + " (copy)"
    with pytest.raises(NotFound):
        await charts.duplicate_chart(session, uuid.uuid4())


async def test_deleting_a_chart_keeps_the_notes_that_showed_it(session):
    bert = await bert_table(session)
    chart = await charts.create_chart(session, "F1", bar(bert))
    note = Note(body="see chart", provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    await session.execute(insert(note_charts).values(note_id=note.id, chart_id=chart.id))
    await session.commit()
    assert next(c for c in await charts.list_charts(session) if c.id == chart.id).note_count == 1

    await charts.delete_chart(session, chart.id)

    with pytest.raises(NotFound):
        await charts.get_chart(session, chart.id)
    assert await session.get(Note, note.id) is not None
    with pytest.raises(NotFound):
        await charts.delete_chart(session, chart.id)
