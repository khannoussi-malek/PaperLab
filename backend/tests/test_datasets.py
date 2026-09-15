import uuid

import pytest
from sqlalchemy import delete, insert

from app.core import datasets
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Chart, Paper, chart_datasets

pytestmark = pytest.mark.anyio


async def make_paper(session, page_count=3) -> Paper:
    paper = Paper(title="Attention Is All You Need", file_path="/nonexistent.pdf", page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


def grid(*rows: tuple[str, ...], names=("Model", "F1"), extracted=False, page=None) -> GridIn:
    """A grid whose cells are the given texts; `extracted` marks every non-empty cell as read from `page`."""

    def cell(text: str, c: int, r: int) -> CellIn:
        if not (extracted and text):
            return CellIn(raw=text)
        box = (72.0 + 100 * c, 100.0 + 14 * r, 90.0 + 100 * c, 110.0)
        return CellIn(raw=text, extracted=text, page=page, bbox=[box])

    return GridIn(
        columns=[ColumnIn(id=None, name=name, unit=None) for name in names],
        rows=[RowIn(id=None, cells=[cell(text, c, r) for c, text in enumerate(row)]) for r, row in enumerate(rows)],
    )


def raws(view) -> list[list[str]]:
    return [[cell.raw for cell in row.cells] for row in view.rows]


async def use_in_chart(session, view, column_id) -> Chart:
    """A chart whose spec names `column_id`, linked to the dataset the way saving a chart links it."""
    chart = Chart(title="F1 by model", spec={"version": 1, "series": [{"y": str(column_id)}]}, spec_version=1)
    session.add(chart)
    await session.flush()
    await session.execute(insert(chart_datasets).values(chart_id=chart.id, dataset_id=view.id))
    await session.commit()
    return chart


async def test_own_data_parses_numbers_and_every_cell_is_human(session):
    view = await datasets.create_dataset(session, "  My runs ", "user", grid(("run 1", "92.0 ± 0.4"), ("run 2", "—")))

    assert (view.name, view.kind, view.paper_id, view.paper_title) == ("My runs", "user", None, None)
    assert (view.row_count, view.column_count) == (2, 2)
    assert [c.name for c in view.columns] == ["Model", "F1"]
    first = view.rows[0].cells[1]
    assert (first.raw, first.value, first.error) == ("92.0 ± 0.4", 92.0, 0.4)
    assert (first.origin, first.original_raw) == ("human", None)
    assert (view.rows[1].cells[1].value, view.rows[0].cells[0].value) == (None, None)
    assert await datasets.get_dataset(session, view.id) == view


async def test_a_captured_table_keeps_what_extraction_read_when_the_owner_changes_a_cell(session):
    paper = await make_paper(session)
    captured = grid(("BERT-B", "88.5"), ("BERT-L", "90.9"), extracted=True, page=2)
    edited = captured.rows[1].cells[1]
    captured.rows[1].cells[1] = CellIn(raw="90.9 ± 0.2", extracted=edited.extracted, page=2, bbox=edited.bbox)

    view = await datasets.create_dataset(
        session, "Table 2: SQuAD 1.1 results.", "table", captured, paper_id=paper.id, page=2, region=(70, 60, 290, 240)
    )

    assert (view.paper_id, view.paper_title, view.page, view.region) == (paper.id, paper.title, 2, [70, 60, 290, 240])
    kept, changed = view.rows[0].cells[1], view.rows[1].cells[1]
    assert (kept.origin, kept.original_raw, kept.page, kept.bbox) == ("extracted", None, 2, [[172, 100, 190, 110]])
    assert (changed.raw, changed.value, changed.error, changed.origin, changed.original_raw) == (
        "90.9 ± 0.2", 90.9, 0.2, "extracted", "90.9"
    )


async def test_a_table_needs_its_paper_page_and_region_and_own_data_has_none(session):
    paper = await make_paper(session, page_count=3)
    table = grid(("a", "1"))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "table", table, paper_id=paper.id, page=2)  # no region
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "table", table, paper_id=paper.id, page=4, region=(1, 2, 3, 4))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "table", table, paper_id=paper.id, page=1, region=(3, 2, 1, 4))
    with pytest.raises(NotFound):
        await datasets.create_dataset(session, "T", "table", table, paper_id=uuid.uuid4(), page=1, region=(1, 2, 3, 4))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", table, paper_id=paper.id)
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", grid(("a", "1"), extracted=True, page=1))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "numbers", table, paper_id=paper.id)


async def test_a_grid_must_be_rectangular_named_and_within_limits(session, monkeypatch):
    ragged = grid(("a", "1"))
    ragged.rows.append(RowIn(id=None, cells=[CellIn(raw="b")]))
    with pytest.raises(InvalidInput, match="row 2 has 1 cells, expected 2"):
        await datasets.create_dataset(session, "T", "user", ragged)
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", GridIn(columns=[], rows=[]))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "   ", "user", grid(("a", "1")))
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "x" * 201, "user", grid(("a", "1")))
    with_ids = grid(("a", "1"))
    with_ids.columns[0] = ColumnIn(id=uuid.uuid4(), name="Model", unit=None)
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", with_ids)

    monkeypatch.setattr(datasets, "MAX_ROWS", 2)
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", grid(("a", "1"), ("b", "2"), ("c", "3")))
    monkeypatch.setattr(datasets, "MAX_COLUMNS", 1)
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, "T", "user", grid(("a", "1")))


async def test_saving_a_grid_keeps_the_ids_of_rows_and_columns_it_still_has(session):
    three_runs = grid(("run 1", "91"), ("run 2", "92"), ("run 3", "93"))
    view = await datasets.create_dataset(session, "Runs", "user", three_runs)
    model, f1 = view.columns
    run1, run2, run3 = view.rows
    # Reorder the columns, add a unit column, drop run 2, put run 3 first, and add run 4.
    new = GridIn(
        columns=[ColumnIn(id=f1.id, name="F1", unit="%"), ColumnIn(id=model.id, name="Run", unit=None),
                 ColumnIn(id=None, name="Seed", unit=None)],
        rows=[
            RowIn(id=run3.id, cells=[CellIn(raw="93.5"), CellIn(raw="run 3"), CellIn(raw="7")]),
            RowIn(id=run1.id, cells=[CellIn(raw="91"), CellIn(raw="run 1"), CellIn(raw="1")]),
            RowIn(id=None, cells=[CellIn(raw="94"), CellIn(raw="run 4"), CellIn(raw="3")]),
        ],
    )  # fmt: skip

    saved = await datasets.save_grid(session, view.id, new)

    assert [c.id for c in saved.columns][:2] == [f1.id, model.id]
    columns = [(c.position, c.name, c.unit) for c in saved.columns]
    assert columns == [(0, "F1", "%"), (1, "Run", None), (2, "Seed", None)]
    assert [r.id for r in saved.rows][:2] == [run3.id, run1.id]
    assert saved.rows[2].id not in {run1.id, run2.id, run3.id}
    assert raws(saved) == [["93.5", "run 3", "7"], ["91", "run 1", "1"], ["94", "run 4", "3"]]
    assert saved.rows[0].cells[0].value == 93.5
    assert (saved.row_count, saved.column_count) == (3, 3)


async def test_saving_marks_a_changed_extracted_cell_and_unmarks_it_when_changed_back(session):
    paper = await make_paper(session)
    view = await datasets.create_dataset(
        session, "T", "table", grid(("BERT-B", "88.5"), extracted=True, page=1), paper_id=paper.id, page=1,
        region=(1, 2, 300, 400),
    )  # fmt: skip

    def with_value(raw: str) -> GridIn:
        cells = [CellIn(raw=c.original_raw or c.raw, extracted=c.original_raw or c.raw, page=c.page, bbox=c.bbox)
                 for c in view.rows[0].cells]  # fmt: skip
        cells[1] = CellIn(raw=raw, extracted="88.5", page=1, bbox=view.rows[0].cells[1].bbox)
        return GridIn(columns=[ColumnIn(id=c.id, name=c.name, unit=c.unit) for c in view.columns],
                      rows=[RowIn(id=view.rows[0].id, cells=cells)])  # fmt: skip

    edited = await datasets.save_grid(session, view.id, with_value("88.6"))
    assert (edited.rows[0].cells[1].raw, edited.rows[0].cells[1].original_raw) == ("88.6", "88.5")
    reverted = await datasets.save_grid(session, view.id, with_value("88.5"))
    assert (reverted.rows[0].cells[1].origin, reverted.rows[0].cells[1].original_raw) == ("extracted", None)


async def test_saving_refuses_ids_from_another_dataset(session):
    mine = await datasets.create_dataset(session, "Mine", "user", grid(("a", "1")))
    other = await datasets.create_dataset(session, "Other", "user", grid(("b", "2")))
    stolen = GridIn(
        columns=[ColumnIn(id=other.columns[0].id, name="x", unit=None), ColumnIn(id=None, name="y", unit=None)],
        rows=[RowIn(id=mine.rows[0].id, cells=[CellIn(raw="a"), CellIn(raw="1")])],
    )
    with pytest.raises(InvalidInput):
        await datasets.save_grid(session, mine.id, stolen)
    with pytest.raises(NotFound):
        await datasets.save_grid(session, uuid.uuid4(), grid(("a", "1")))


async def test_removing_a_column_a_chart_uses_needs_force_and_keeps_the_chart(session):
    runs = grid(("run 1", "91", "7"), names=("Model", "F1", "Seed"))
    view = await datasets.create_dataset(session, "Runs", "user", runs)
    model, f1, seed = view.columns
    chart = await use_in_chart(session, view, f1.id)

    shown = await datasets.get_dataset(session, view.id)
    assert [(c.id, c.title, c.column_ids) for c in shown.charts] == [(chart.id, "F1 by model", [f1.id])]

    def keeping(*columns) -> GridIn:
        values = {model.id: "run 1", f1.id: "91", seed.id: "7"}
        return GridIn(
            columns=[ColumnIn(id=c.id, name=c.name, unit=None) for c in columns],
            rows=[RowIn(id=view.rows[0].id, cells=[CellIn(raw=values[c.id]) for c in columns])],
        )

    # Seed isn't in the chart: removing it needs no force.
    assert (await datasets.save_grid(session, view.id, keeping(model, f1))).column_count == 2
    with pytest.raises(Conflict, match="used_by_charts"):
        await datasets.save_grid(session, view.id, keeping(model))
    forced = await datasets.save_grid(session, view.id, keeping(model), force=True)

    assert (forced.column_count, forced.charts[0].column_ids) == (1, [])
    assert await session.get(Chart, chart.id) is not None


async def test_deleting_a_dataset_a_chart_uses_needs_force(session):
    view = await datasets.create_dataset(session, "Runs", "user", grid(("run 1", "91")))
    chart = await use_in_chart(session, view, view.columns[1].id)

    with pytest.raises(Conflict, match="used_by_charts"):
        await datasets.delete_dataset(session, view.id)
    await datasets.delete_dataset(session, view.id, force=True)

    with pytest.raises(NotFound):
        await datasets.get_dataset(session, view.id)
    assert await session.get(Chart, chart.id) is not None
    with pytest.raises(NotFound):
        await datasets.delete_dataset(session, view.id)


async def test_lists_a_papers_datasets_or_all_of_them_with_paper_titles(session):
    paper, other = await make_paper(session), await make_paper(session)
    region = (1, 2, 300, 400)
    later_page = await datasets.create_dataset(session, "p3", "table", grid(("a", "1")), paper_id=paper.id, page=3,
                                               region=region)  # fmt: skip
    first_page = await datasets.create_dataset(session, "p1", "table", grid(("a", "1")), paper_id=paper.id, page=1,
                                               region=region)  # fmt: skip
    elsewhere = await datasets.create_dataset(session, "o", "table", grid(("a", "1")), paper_id=other.id, page=1,
                                              region=region)  # fmt: skip
    mine = await datasets.create_dataset(session, "mine", "user", grid(("a", "1")))

    assert [d.id for d in await datasets.list_datasets(session, paper.id)] == [first_page.id, later_page.id]
    everything = {d.id: d for d in await datasets.list_datasets(session)}
    assert {first_page.id, later_page.id, elsewhere.id, mine.id} <= everything.keys()
    assert (everything[mine.id].paper_title, everything[elsewhere.id].paper_title) == (None, paper.title)
    with pytest.raises(NotFound):
        await datasets.list_datasets(session, uuid.uuid4())


async def test_rename_strips_and_checks_the_name(session):
    view = await datasets.create_dataset(session, "Runs", "user", grid(("a", "1")))

    assert (await datasets.rename_dataset(session, view.id, "  Seeds ")).name == "Seeds"
    with pytest.raises(InvalidInput):
        await datasets.rename_dataset(session, view.id, " ")
    with pytest.raises(NotFound):
        await datasets.rename_dataset(session, uuid.uuid4(), "x")


async def test_a_deleted_papers_table_stays_with_no_paper(session):
    paper = await make_paper(session)
    view = await datasets.create_dataset(session, "T", "table", grid(("a", "1"), extracted=True, page=1),
                                         paper_id=paper.id, page=1, region=(1, 2, 300, 400))  # fmt: skip
    await session.execute(delete(Paper).where(Paper.id == paper.id))
    await session.commit()

    kept = await datasets.get_dataset(session, view.id)
    assert (kept.paper_id, kept.paper_title, kept.rows[0].cells[1].page) == (None, None, 1)
