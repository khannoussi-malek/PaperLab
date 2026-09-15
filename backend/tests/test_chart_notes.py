import uuid

import pytest

from app.core import capture, charts, datasets, notes
from app.core.chart_spec import ChartSpecAdapter
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.errors import InvalidInput, NotFound
from app.models import Paper, Provenance

pytestmark = pytest.mark.anyio

REGION = (70.0, 60.0, 290.0, 240.0)


async def make_paper(session, title="BERT") -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=9)
    session.add(paper)
    await session.commit()
    return paper


def two_columns(*rows: tuple[str, str], page: int | None = None) -> GridIn:
    def cell(text):
        return CellIn(raw=text, extracted=text, page=page, bbox=[(72.0, 100.0, 90.0, 110.0)]) if page else CellIn(text)

    return GridIn(
        columns=[ColumnIn(None, "System", None), ColumnIn(None, "F1", None)],
        rows=[RowIn(None, [cell(a), cell(b)]) for a, b in rows],
    )


def bar(*sources: datasets.DatasetView, y_column: int = 1, rows=None):
    return ChartSpecAdapter.validate_python({"type": "bar", "series": [
        {"id": f"s{i}", "dataset_id": str(d.id), "y": str(d.columns[y_column].id),
         "rows": None if rows is None else [str(r) for r in rows]}
        for i, d in enumerate(sources)
    ]})  # fmt: skip


async def a_note(session, paper: Paper) -> notes.NoteView:
    anchor = notes.Anchor(paper_id=paper.id, page=1, bbox=[(72.0, 400.0, 290.0, 410.0)], quoted_text="a quote")
    return await notes.create_human_note(session, "my reading", anchor)


async def test_a_note_shows_the_charts_attached_to_it_once_each(session):
    paper = await make_paper(session)
    mine = await datasets.create_dataset(session, "My runs", "user", two_columns(("mine", "92")))
    chart = await charts.create_chart(session, "F1", bar(mine))
    note = await a_note(session, paper)

    attached = await notes.attach_chart(session, note.id, chart.id)
    again = await notes.attach_chart(session, note.id, chart.id)

    assert attached.charts == again.charts == [notes.ChartRef(chart.id, "F1")]
    assert (attached.provenance, attached.body) == (Provenance.HUMAN, "my reading")
    assert (await notes.list_notes_for_paper(session, paper.id))[0].charts == [notes.ChartRef(chart.id, "F1")]
    assert (await charts.get_chart(session, chart.id)).note_ids == [note.id]

    detached = await notes.detach_chart(session, note.id, chart.id)
    assert detached.charts == []
    assert (await notes.detach_chart(session, note.id, chart.id)).charts == []  # detaching twice is fine


async def test_attaching_needs_an_existing_note_and_chart(session):
    paper = await make_paper(session)
    mine = await datasets.create_dataset(session, "My runs", "user", two_columns(("mine", "92")))
    chart = await charts.create_chart(session, "F1", bar(mine))
    note = await a_note(session, paper)

    with pytest.raises(NotFound):
        await notes.attach_chart(session, uuid.uuid4(), chart.id)
    with pytest.raises(NotFound):
        await notes.attach_chart(session, note.id, uuid.uuid4())
    with pytest.raises(NotFound):
        await notes.detach_chart(session, uuid.uuid4(), chart.id)


async def test_a_chart_note_is_anchored_on_each_table_region_and_each_captured_number(session):
    bert, xlnet = await make_paper(session, "BERT"), await make_paper(session, "XLNet")
    table = await datasets.create_dataset(session, "Table 2: SQuAD 1.1 results.", "table",
                                          two_columns(("BERT-L", "90.9"), page=7), paper_id=bert.id, page=7,
                                          region=REGION)  # fmt: skip
    first = await capture.add_number(session, xlnet.id, "XLNet F1", "94.5", "F1", 7, [(100.0, 300.0, 140.0, 312.0)])
    await capture.add_number(session, xlnet.id, "not charted", "1.0", "", 8, [(100.0, 500.0, 140.0, 512.0)])
    numbers = await datasets.get_dataset(session, first.dataset_id)
    mine = await datasets.create_dataset(session, "My runs", "user", two_columns(("mine", "92")))
    # The numbers series charts only the first captured number.
    spec = ChartSpecAdapter.validate_python({"type": "bar", "series": [
        {"id": "t", "dataset_id": str(table.id), "y": str(table.columns[1].id)},
        {"id": "n", "dataset_id": str(numbers.id), "y": str(numbers.columns[1].id), "rows": [str(first.row_id)]},
        {"id": "m", "dataset_id": str(mine.id), "y": str(mine.columns[1].id)},
    ]})  # fmt: skip
    chart = await charts.create_chart(session, "SQuAD F1", spec)

    note = await notes.create_chart_note(session, chart.id, await charts.chart_anchors(session, chart.id))

    assert (note.body, note.provenance, note.charts) == ("", Provenance.HUMAN, [notes.ChartRef(chart.id, "SQuAD F1")])
    assert sorted((a.paper_id == bert.id, a.page, a.bbox, a.quoted_text) for a in note.anchors) == [
        (False, 7, [(100.0, 300.0, 140.0, 312.0)], "94.5"),
        (True, 7, [REGION], "Table 2: SQuAD 1.1 results."),
    ]
    assert [n.id for n in await notes.list_notes_for_paper(session, xlnet.id)] == [note.id]


async def test_a_chart_of_own_data_only_has_nothing_to_anchor_a_note_on(session):
    mine = await datasets.create_dataset(session, "My runs", "user", two_columns(("mine", "92")))
    chart = await charts.create_chart(session, "Mine", bar(mine))

    with pytest.raises(InvalidInput, match="chart_has_no_paper_data"):
        await charts.chart_anchors(session, chart.id)
    with pytest.raises(NotFound):
        await charts.chart_anchors(session, uuid.uuid4())
    with pytest.raises(InvalidInput):
        await notes.create_chart_note(session, chart.id, [])
