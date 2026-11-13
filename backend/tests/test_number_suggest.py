"""AI number suggestions (D33, M13's AI half): the model proposes numbers with quotes; PaperLab keeps only those it
can find in the section, and an added number's label is marked as the model's."""

import json
import uuid

import pytest

from app.core import capture, datasets, number_suggest
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.errors import InvalidInput
from app.models import Chunk, Paper
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio

RESULTS = "Our model reaches an accuracy of 92.3% on the test set, while the baseline stays at 85.1%."


class Replying(FakeLLM):
    def __init__(self, reply: dict):
        super().__init__()
        self.reply = json.dumps(reply)

    async def stream(self, system, prompt):
        self.calls.append((system, prompt))
        yield self.reply


async def a_paper(session) -> Paper:
    paper = Paper(title="BERT", file_path="/nonexistent.pdf", page_count=9)
    session.add(paper)
    await session.flush()
    session.add_all([
        Chunk(paper_id=paper.id, ordinal=0, page=2, bbox=[[72, 100, 300, 120]], section_title="Method",
              text="We train for 3 epochs with a batch size of 32.", embed_model="test", strategy_ver=1),
        Chunk(paper_id=paper.id, ordinal=1, page=5, bbox=[[72, 200, 300, 220]], section_title="Results",
              text=RESULTS, embed_model="test", strategy_ver=1),
    ])  # fmt: skip
    await session.commit()
    return paper


async def test_only_numbers_quoted_from_the_section_survive(session):
    paper = await a_paper(session)
    llm = Replying({"numbers": [
        {"label": "Accuracy (ours)", "value": "92.3", "unit": "%",
         "quote": "reaches an accuracy of 92.3% on the test set"},
        {"label": "Baseline accuracy", "value": "88.0", "unit": "%", "quote": "the baseline stays at 85.1%"},
        {"label": "Epochs", "value": "3", "unit": "", "quote": "We train for 3 epochs"},
        {"label": "F1", "value": "90", "unit": "", "quote": "an F1 of 90 on every split"},
    ]})  # fmt: skip
    found = await number_suggest.suggest(session, paper.id, "Results", llm)
    assert [(s.label, s.raw, s.unit, s.page) for s in found.suggestions] == [("Accuracy (ours)", "92.3", "%", 5)]
    assert found.suggestions[0].bbox == [(72.0, 200.0, 300.0, 220.0)]
    assert found.dropped == 3
    assert RESULTS in llm.calls[0][1] and "3 epochs" not in llm.calls[0][1]


async def test_an_unknown_section_is_refused(session):
    paper = await a_paper(session)
    with pytest.raises(InvalidInput, match="unknown_section"):
        await number_suggest.suggest(session, paper.id, "Appendix Z", Replying({"numbers": []}))


async def test_an_added_suggestion_marks_its_label_as_the_models(session):
    paper = await a_paper(session)
    added = await capture.add_number(session, paper.id, "Accuracy (ours)", "92.3", "%", 5,
                                     [(72.0, 200.0, 300.0, 220.0)], suggested=True)
    view = await datasets.get_dataset(session, added.dataset_id)
    label, value, unit = view.rows[0].cells
    assert (label.raw, label.origin, value.origin, unit.origin) == ("Accuracy (ours)", "llm", "extracted", "human")


async def test_a_grid_keeps_a_suggested_cell_marked_and_shows_an_edit(session):
    paper = await a_paper(session)
    added = await capture.add_number(session, paper.id, "Acc", "92.3", "%", 5, [(72.0, 200.0, 300.0, 220.0)],
                                     suggested=True)
    view = await datasets.get_dataset(session, added.dataset_id)
    columns = [ColumnIn(c.id, c.name, c.unit) for c in view.columns]
    row = view.rows[0]
    cells = [CellIn(raw="Accuracy", suggested="Acc")] + [
        CellIn(raw=c.raw, extracted=c.raw if c.origin == "extracted" else None, page=c.page, bbox=c.bbox)
        for c in row.cells[1:]
    ]
    saved = await datasets.save_grid(session, added.dataset_id, GridIn(columns, [RowIn(row.id, cells)]))
    label = saved.rows[0].cells[0]
    assert (label.raw, label.origin, label.original_raw) == ("Accuracy", "llm", "Acc")


async def test_own_data_cannot_claim_a_models_cell(session):
    grid = GridIn([ColumnIn(None, "A", None)], [RowIn(None, [CellIn(raw="x", suggested="x")])])
    with pytest.raises(InvalidInput):
        await datasets.create_dataset(session, f"mine {uuid.uuid4().hex[:6]}", "user", grid)


async def test_the_route_returns_the_kept_suggestions(client, session, fake_llm):
    paper = await a_paper(session)
    resp = await client.post(f"/api/papers/{paper.id}/numbers/suggestions", json={"section_title": "Results"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["suggestions"] and all(s["page"] == 5 for s in body["suggestions"])


async def test_a_value_must_be_a_whole_number_of_its_quote_and_a_unit_must_be_in_it(session):
    paper = await a_paper(session)
    llm = Replying({"numbers": [
        {"label": "Accuracy", "value": "92", "unit": "%", "quote": "reaches an accuracy of 92.3% on the test set"},
        {"label": "Baseline", "value": "85.1", "unit": "ms", "quote": "while the baseline stays at 85.1%"},
        {"label": "Ours", "value": "92.3", "unit": "%", "quote": "reaches an accuracy of 92.3% on the test set"},
        {"label": "Ours again", "value": "92.3", "unit": "%", "quote": "reaches an accuracy of 92.3% on the test set"},
    ]})  # fmt: skip
    found = await number_suggest.suggest(session, paper.id, "Results", llm)
    assert [(s.label, s.raw, s.unit) for s in found.suggestions] == [
        ("Baseline", "85.1", ""), ("Ours", "92.3", "%"), ("Ours again", "92.3", "%"),
    ]
    assert found.dropped == 1


async def test_one_malformed_item_does_not_sink_the_others(session):
    paper = await a_paper(session)
    llm = Replying({"numbers": [
        {"label": "x" * 500, "value": "92.3", "unit": "%", "quote": "reaches an accuracy of 92.3% on the test set"},
        {"label": "Baseline", "value": "85.1", "unit": "%", "quote": "while the baseline stays at 85.1%"},
    ]})  # fmt: skip
    found = await number_suggest.suggest(session, paper.id, "Results", llm)
    assert [s.label for s in found.suggestions] == ["Baseline"] and found.dropped == 1


async def test_a_reply_that_is_not_a_list_of_numbers_says_so(session):
    paper = await a_paper(session)

    class Rambling(Replying):
        async def stream(self, system, prompt):
            yield "I found several numbers."

    with pytest.raises(InvalidInput, match="couldn't read"):
        await number_suggest.suggest(session, paper.id, "Results", Rambling({}))
