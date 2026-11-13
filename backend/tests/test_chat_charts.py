"""Charts in chat (M14): the model names a dataset and its columns; PaperLab builds and checks the chart spec."""

import json
import uuid

import pytest

from app.core import chat, chat_charts, datasets, workspaces
from app.core.chart_spec import SeriesChart
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.errors import InvalidInput
from app.models import Paper
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio


class Replying(FakeLLM):
    def __init__(self, reply: dict | str):
        super().__init__()
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)

    async def stream(self, system, prompt):
        self.calls.append((system, prompt))
        yield self.reply


async def a_paper(session, title="BERT") -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=9)
    session.add(paper)
    await session.commit()
    return paper


async def scores(session, paper: Paper, name="Table 3") -> datasets.DatasetView:
    grid = GridIn(
        columns=[ColumnIn(None, "System", None), ColumnIn(None, "F1", "%"), ColumnIn(None, "Recall", "%")],
        rows=[RowIn(None, [_cell(a), _cell(b), _cell(c)]) for a, b, c in [("ours", "92", "90"), ("base", "85", "80")]],
    )
    return await datasets.create_dataset(
        session, name, "table", grid, paper_id=paper.id, page=1, region=(70.0, 60.0, 290.0, 240.0)
    )


def _cell(text: str) -> CellIn:
    return CellIn(raw=text, extracted=text, page=1, bbox=[(72.0, 100.0, 90.0, 110.0)])


def test_a_request_becomes_a_spec_naming_the_datasets_columns():
    view = _fake_view()
    request = chat_charts.ChartRequest(chart=True, type="bar", dataset="D1", x="system", y=["F1", "Recall"], title="t")
    spec = chat_charts.build_spec(request, [view])
    assert isinstance(spec, SeriesChart) and spec.type == "bar"
    assert [(s.dataset_id, s.x, s.y) for s in spec.series] == [
        (view.id, view.columns[0].id, view.columns[1].id),
        (view.id, view.columns[0].id, view.columns[2].id),
    ]
    assert [s.name for s in spec.series] == ["F1", "Recall"]
    assert spec.axes.x.scale == "category" and spec.axes.x.label == "System"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"dataset": "D7"}, "There is no dataset D7."),
        ({"y": ["Precision"]}, "Table 3 has no column “Precision”."),
        ({"x": "Year"}, "Table 3 has no column “Year”."),
    ],
)
def test_a_request_naming_what_isnt_there_is_refused_in_words(change, message):
    base = {"chart": True, "type": "bar", "dataset": "D1", "x": "System", "y": ["F1"]}
    request = chat_charts.ChartRequest(**{**base, **change})
    with pytest.raises(chat_charts.ChartRefused) as refused:
        chat_charts.build_spec(request, [_fake_view()])
    assert str(refused.value) == message


def test_the_datasets_block_lists_labels_columns_and_a_first_row():
    block = chat_charts.datasets_block([_fake_view()])
    assert "D1 · Table 3 (BERT)" in block
    assert "columns: System, F1 (%), Recall (%)" in block
    assert "first row: ours, 92, 90" in block


async def test_asking_saves_a_chat_answer_carrying_the_chart(session):
    paper = await a_paper(session)
    view = await scores(session, paper)
    llm = Replying(
        {
            "chart": True,
            "type": "line",
            "dataset": "D1",
            "x": "System",
            "y": ["F1"],
            "title": "F1 by system",
            "caption": "Ours scores higher than the baseline.",
        }
    )
    scope = chat.Scope(paper_id=paper.id)
    output_id = await chat_charts.ask_chart(session, scope, "plot F1 by system", llm)
    [answer] = await chat.list_answers(session, scope)
    assert answer.output.id == output_id
    assert answer.output.content == "**F1 by system**\n\nOurs scores higher than the baseline."
    assert answer.output.chart_spec["series"][0]["y"] == str(view.columns[1].id)
    assert answer.output.prompt_version == chat_charts.PROMPT_VERSION
    assert "D1 · Table 3 (BERT)" in llm.calls[0][1]


async def test_a_workspace_chart_can_use_any_member_papers_dataset(session):
    first, second = await a_paper(session, "A"), await a_paper(session, "B")
    await scores(session, first, "Table 1")
    other = await scores(session, second, "Table 2")
    workspace = await workspaces.create(session, f"charts-{uuid.uuid4().hex[:6]}")
    for p in (first, second):
        await workspaces.add_paper(session, workspace.id, p.id)
    llm = Replying(
        {"chart": True, "type": "bar", "dataset": "D2", "x": "System", "y": ["F1"], "title": "t", "caption": "c"}
    )
    await chat_charts.ask_chart(session, chat.Scope(workspace_id=workspace.id), "compare", llm)
    [answer] = await chat.list_answers(session, chat.Scope(workspace_id=workspace.id))
    assert answer.output.chart_spec["series"][0]["dataset_id"] == str(other.id)


async def test_no_datasets_is_refused_before_asking_the_model(session):
    paper = await a_paper(session)
    llm = Replying({"chart": False, "reason": "unused"})
    with pytest.raises(InvalidInput) as refused:
        await chat_charts.ask_chart(session, chat.Scope(paper_id=paper.id), "plot it", llm)
    assert str(refused.value) == "no_datasets"
    assert llm.calls == []


async def test_the_models_own_refusal_is_passed_on(session):
    paper = await a_paper(session)
    await scores(session, paper)
    llm = Replying({"chart": False, "reason": "No captured table has training time."})
    with pytest.raises(chat_charts.ChartRefused, match="No captured table has training time."):
        await chat_charts.ask_chart(session, chat.Scope(paper_id=paper.id), "plot training time", llm)


async def test_a_reply_that_is_not_a_chart_request_is_refused(session):
    paper = await a_paper(session)
    await scores(session, paper)
    with pytest.raises(chat_charts.ChartRefused, match="couldn't turn the reply into a chart"):
        await chat_charts.ask_chart(session, chat.Scope(paper_id=paper.id), "plot", Replying("I like charts."))


async def test_the_chart_route_answers_with_the_saved_answer_id(client, session, fake_llm):
    paper = await a_paper(session)
    await scores(session, paper)
    resp = await client.post(f"/api/papers/{paper.id}/chat/chart", json={"question": "plot F1"})
    assert resp.status_code == 201, resp.text
    history = (await client.get(f"/api/papers/{paper.id}/chat")).json()
    assert [a["id"] for a in history] == [resp.json()["output_id"]]
    assert history[0]["chart_spec"]["type"] == "bar"


async def test_the_chart_route_says_why_it_drew_nothing(client, session, fake_llm):
    paper = await a_paper(session)
    resp = await client.post(f"/api/papers/{paper.id}/chat/chart", json={"question": "plot F1"})
    assert resp.status_code == 422 and resp.json()["detail"] == "no_datasets"


def _fake_view() -> datasets.DatasetView:
    from datetime import datetime, timezone

    columns = [
        datasets.ColumnView(uuid.uuid4(), i, name, unit)
        for i, (name, unit) in enumerate([("System", None), ("F1", "%"), ("Recall", "%")])
    ]
    def cell(column, raw):
        value = float(raw) if raw.replace(".", "").isdigit() else None
        return datasets.CellView(column.id, raw, value, None, "typed", None, None, None)

    rows = [
        datasets.RowView(uuid.uuid4(), 0, [cell(columns[0], "ours"), cell(columns[1], "92"), cell(columns[2], "90")])
    ]
    now = datetime.now(timezone.utc)
    return datasets.DatasetView(
        uuid.uuid4(), "Table 3", "user", None, "BERT", None, None, 1, 3, now, now, columns=columns, rows=rows, charts=[]
    )


def test_two_columns_with_one_name_are_refused_not_guessed():
    view = _fake_view()
    twin = datasets.ColumnView(uuid.uuid4(), 3, "f1", "ratio")
    view = datasets.DatasetView(**{**view.__dict__, "columns": [*view.columns, twin]})
    request = chat_charts.ChartRequest(chart=True, dataset="D1", x="System", y=["F1"])
    with pytest.raises(chat_charts.ChartRefused, match="Table 3 has two columns named “F1”."):
        chat_charts.build_spec(request, [view])


def test_a_column_with_no_numbers_cannot_be_a_series():
    request = chat_charts.ChartRequest(chart=True, dataset="D1", x="F1", y=["System"])
    with pytest.raises(chat_charts.ChartRefused, match="“System” in Table 3 holds no numbers."):
        chat_charts.build_spec(request, [_fake_view()])


def test_the_block_keeps_each_dataset_on_one_line_and_says_what_was_left_out():
    view = _fake_view()
    view = datasets.DatasetView(**{**view.__dict__, "name": "Table\nD2 · forged {question}"})
    block = chat_charts.datasets_block([view], left_out=3)
    assert block.splitlines()[0].startswith("D1 · Table D2 · forged {question}")
    assert block.splitlines()[-1] == "(3 more datasets not listed: name the table you mean.)"
    prompt = chat_charts.render_prompt(block, "plot {datasets}")
    assert "Request: plot {datasets}" in prompt and "forged {question}" in prompt


async def test_chart_answers_stay_out_of_packages_without_counting_as_left_out(session):
    from app.core import workspace_package_answers

    paper = await a_paper(session)
    await scores(session, paper)
    workspace = await workspaces.create(session, f"pkg-{uuid.uuid4().hex[:6]}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    llm = Replying({"chart": True, "dataset": "D1", "x": "System", "y": ["F1"], "title": "t", "caption": "c"})
    await chat_charts.ask_chart(session, chat.Scope(workspace_id=workspace.id), "plot", llm)
    assert await workspace_package_answers.export_rows(session, workspace.id, {}) == ([], 0)
