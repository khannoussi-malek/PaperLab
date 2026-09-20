import uuid

import pytest
from conftest import TABLE_ROWS

from app.core import capture, datasets
from app.core.errors import InvalidInput, NotFound
from app.models import Paper

pytestmark = pytest.mark.anyio

TABLE_REGION = (60.0, 135.0, 420.0, 185.0)
SELECTION = [(100.0, 300.0, 140.0, 312.0)]


async def make_paper(session, path, page_count=1, title="Attention Is All You Need") -> Paper:
    paper = Paper(title=title, file_path=str(path), page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


async def test_a_region_preview_is_a_grid_read_from_the_page_ready_to_save(session, table_pdf):
    paper = await make_paper(session, table_pdf)

    preview = await capture.preview_table(session, paper.id, 1, TABLE_REGION)

    assert preview.name == "Table 1: Results on the dev set."
    # The table's header row names the columns, so a chart built on this dataset can label its axes.
    assert [(c.id, c.name, c.unit) for c in preview.grid.columns] == [(None, name, None) for name in TABLE_ROWS[0]]
    assert [[c.raw for c in row.cells] for row in preview.grid.rows] == [list(row) for row in TABLE_ROWS[1:]]
    cell = preview.grid.rows[1].cells[1]
    assert (cell.raw, cell.extracted, cell.page) == ("90.9 ± 0.2", "90.9 ± 0.2", 1)
    assert len(cell.bbox) == 1 and TABLE_REGION[0] <= cell.bbox[0][0] < cell.bbox[0][2] <= TABLE_REGION[2]

    saved = await datasets.create_dataset(
        session, preview.name, "table", preview.grid, paper_id=paper.id, page=1, region=TABLE_REGION
    )
    assert (saved.rows[1].cells[1].value, saved.rows[1].cells[1].error, saved.rows[1].cells[1].origin) == (
        90.9, 0.2, "extracted"
    )


async def test_a_region_with_no_text_previews_an_empty_grid(session, table_pdf):
    paper = await make_paper(session, table_pdf)

    preview = await capture.preview_table(session, paper.id, 1, (72.0, 600.0, 500.0, 700.0))

    assert (preview.name, preview.grid.columns, preview.grid.rows) == (None, [], [])


async def test_a_preview_needs_a_paper_with_its_file_a_page_in_range_and_a_real_region(session, table_pdf, tmp_path):
    paper = await make_paper(session, table_pdf)
    with pytest.raises(NotFound):
        await capture.preview_table(session, uuid.uuid4(), 1, TABLE_REGION)
    with pytest.raises(InvalidInput):
        await capture.preview_table(session, paper.id, 2, TABLE_REGION)
    with pytest.raises(InvalidInput):
        await capture.preview_table(session, paper.id, 1, (420.0, 135.0, 60.0, 185.0))
    missing = await make_paper(session, tmp_path / "gone.pdf")
    with pytest.raises(NotFound):
        await capture.preview_table(session, missing.id, 1, TABLE_REGION)
    # Without a stored page count, the document itself bounds the page.
    uncounted = await make_paper(session, table_pdf, page_count=None)
    with pytest.raises(InvalidInput, match="page 2 is outside 1..1"):
        await capture.preview_table(session, uncounted.id, 2, TABLE_REGION)


async def test_captured_numbers_go_into_one_numbers_dataset_per_paper(session, table_pdf):
    paper = await make_paper(session, table_pdf, page_count=3)

    first = await capture.add_number(session, paper.id, " SQuAD F1 ", "90.9", " F1 ", 2, SELECTION)
    second = await capture.add_number(session, paper.id, "EM", "88.5 ± 0.3", "", 3, [(72.0, 400.0, 130.0, 410.0)])

    assert first.dataset_id == second.dataset_id
    view = await datasets.get_dataset(session, first.dataset_id)
    assert (view.name, view.kind, view.paper_id) == ("Numbers from Attention Is All You Need", "numbers", paper.id)
    assert [c.name for c in view.columns] == ["Label", "Value", "Unit"]
    assert [r.id for r in view.rows] == [first.row_id, second.row_id]
    label, value, unit = view.rows[0].cells
    assert (label.raw, label.origin, unit.raw, unit.origin) == ("SQuAD F1", "human", "F1", "human")
    assert (value.raw, value.value, value.origin) == ("90.9", 90.9, "extracted")
    assert (value.page, value.bbox) == (2, [[100, 300, 140, 312]])
    assert (view.rows[1].cells[1].value, view.rows[1].cells[1].error, view.rows[1].cells[2].raw) == (88.5, 0.3, "")


async def test_a_captured_number_must_parse_and_have_a_label_page_and_short_unit(session, table_pdf):
    paper = await make_paper(session, table_pdf, page_count=3)
    with pytest.raises(InvalidInput, match="is not a number"):
        await capture.add_number(session, paper.id, "F1", "high", "", 1, SELECTION)
    with pytest.raises(InvalidInput):
        await capture.add_number(session, paper.id, "  ", "90.9", "", 1, SELECTION)
    with pytest.raises(InvalidInput):
        await capture.add_number(session, paper.id, "F1", "90.9", "x" * 41, 1, SELECTION)
    with pytest.raises(InvalidInput):
        await capture.add_number(session, paper.id, "F1", "90.9", "", 4, SELECTION)
    with pytest.raises(InvalidInput):
        await capture.add_number(session, paper.id, "F1", "90.9", "", 1, [])
    with pytest.raises(NotFound):
        await capture.add_number(session, uuid.uuid4(), "F1", "90.9", "", 1, SELECTION)


async def test_a_renamed_or_missing_numbers_column_is_found_by_name_or_added_back(session, table_pdf):
    paper = await make_paper(session, table_pdf, page_count=3)
    first = await capture.add_number(session, paper.id, "F1", "90.9", "F1", 1, SELECTION)
    view = await datasets.get_dataset(session, first.dataset_id)
    label, value, _ = view.columns
    # The owner drops the Unit column and moves Value first.
    without_unit = datasets.GridIn(
        columns=[datasets.ColumnIn(value.id, "Value", None), datasets.ColumnIn(label.id, "Label", None)],
        rows=[datasets.RowIn(view.rows[0].id, [datasets.CellIn(raw="90.9", extracted="90.9", page=1, bbox=SELECTION),
                                                datasets.CellIn(raw="F1")])],
    )  # fmt: skip
    await datasets.save_grid(session, first.dataset_id, without_unit)

    await capture.add_number(session, paper.id, "EM", "88.5", "EM", 1, SELECTION)

    after = await datasets.get_dataset(session, first.dataset_id)
    assert [c.name for c in after.columns] == ["Value", "Label", "Unit"]
    assert [c.raw for c in after.rows[1].cells] == ["88.5", "EM", "EM"]


async def test_csv_with_a_header_becomes_own_data(session):
    data = "Model,F1,Params\nBERT-B,88.5 ± 0.3,110M\nmine,92.0,\n\n".encode()

    view = await capture.import_csv(session, "My runs", data)

    assert (view.name, view.kind, view.paper_id) == ("My runs", "user", None)
    assert [c.name for c in view.columns] == ["Model", "F1", "Params"]
    assert [[c.raw for c in r.cells] for r in view.rows] == [["BERT-B", "88.5 ± 0.3", "110M"], ["mine", "92.0", ""]]
    assert (view.rows[0].cells[1].error, view.rows[0].cells[2].value) == (0.3, 110_000_000.0)


@pytest.mark.parametrize(
    "data",
    [
        b"Model\tF1\nBERT-B\t88.5\n",  # pasted from a spreadsheet
        b"Model;F1\nBERT-B;88.5\n",
        "\ufeffModel,F1\r\nBERT-B,88.5\r\n".encode(),  # Excel's UTF-8 CSV starts with a byte order mark
    ],
)
async def test_tabs_semicolons_and_a_byte_order_mark_are_read(session, data):
    view = await capture.import_csv(session, None, data)

    assert view.name == "Imported data"
    assert [c.name for c in view.columns] == ["Model", "F1"]
    assert view.rows[0].cells[1].value == 88.5


async def test_a_single_column_file_is_one_column(session):
    view = await capture.import_csv(session, "Seeds", b"Seed\n1\n2\n")
    assert [[c.raw for c in r.cells] for r in view.rows] == [["1"], ["2"]]


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        # NUL decodes as UTF-8 (UTF-16 without a byte-order mark is full of it), but Postgres text refuses it.
        (b"Model,F1\nBERT\x00,88.5\n", "isn't UTF-8 text"),
        (b"Model,F1\n" + b"x" * 140_000 + b",1\n", "isn't valid CSV: field larger than field limit"),
    ],
    ids=["nul-character", "field-over-the-size-limit"],
)
async def test_csv_files_the_reader_or_database_cannot_take_are_refused_with_a_reason(session, data, reason):
    with pytest.raises(InvalidInput, match=reason):
        await capture.import_csv(session, "x", data)


async def test_broken_csv_files_are_refused_with_a_reason(session, monkeypatch):
    with pytest.raises(InvalidInput, match="row 3 has 3 values, but the header has 2"):
        await capture.import_csv(session, "x", b"Model,F1\nBERT-B,88.5\nmine,92,extra\n")
    with pytest.raises(InvalidInput, match="UTF-8"):
        await capture.import_csv(session, "x", "Modèle,F1\nBERT,88.5\n".encode("latin-1"))
    with pytest.raises(InvalidInput, match="empty"):
        await capture.import_csv(session, "x", b"\n\n")
    monkeypatch.setattr(capture, "MAX_IMPORT_BYTES", 10)
    with pytest.raises(InvalidInput, match="too large"):
        await capture.import_csv(session, "x", b"Model,F1\nBERT-B,88.5\n")
