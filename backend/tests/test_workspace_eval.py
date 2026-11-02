import uuid

import pytest
from conftest import unit_vector
from sqlalchemy import insert

from app.core import retrieval
from app.models import Chunk, Paper, Workspace, workspace_papers
from evals import workspace_run

pytestmark = pytest.mark.anyio


def key(workspace: str) -> str:
    return f"""
workspace: "{workspace}"
questions:
  - id: both
    question: Which two passages?
    needs:
      - - {{paper: "Label", contains: "THE   first target"}}
      - - {{paper: "Label, EU", contains: "the second target"}}
  - id: half
    seen: true
    question: Only half of it?
    needs:
      - - {{paper: "Label", contains: "the first target"}}
      - - {{paper: "Label, EU", contains: "a far passage"}}
  - id: none
    question: Nothing answers this?
    needs: []
"""


async def seed(session, embedder) -> str:
    """Two papers titled "Label" and "Label, EU" (one is a prefix of the other) in a fresh workspace; each question
    embeds right onto its paper's target chunk."""
    workspace = Workspace(name=f"Workspace eval {uuid.uuid4()}")
    papers = [Paper(title=title, file_path=f"/{title}.pdf", status="ready") for title in ("Label", "Label, EU")]
    session.add_all([workspace, *papers])
    await session.flush()
    texts = {
        papers[0].id: [f"label filler {i}" for i in range(6)] + ["Here is the first target passage."],
        papers[1].id: [f"eu filler {i}" for i in range(6)] + ["Here is the second target.", "Then a far passage."],
    }
    first, second = unit_vector("Here is the first target passage."), unit_vector("Here is the second target.")
    near = [a + b for a, b in zip(first, second, strict=True)]
    far = [-x for x in near]  # the far passage points straight away from both questions: last, whatever the seed
    session.add_all(
        Chunk(
            paper_id=paper_id, ordinal=i, page=i + 1, bbox=[[1, 2, 3, 4]], text=text,
            embedding=far if "far passage" in text else unit_vector(text), embed_model="test", strategy_ver=1,
        )
        for paper_id, paper_texts in texts.items()
        for i, text in enumerate(paper_texts)
    )
    await session.execute(insert(workspace_papers), [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers])
    await session.commit()
    for question in ("Which two passages?", "Only half of it?"):
        embedder.vectors[f"search_query: {question}"] = near
    return workspace.name


def write(tmp_path, text: str):
    path = tmp_path / "workspace_questions.yaml"
    path.write_text(text)
    return path


async def test_a_question_counts_only_when_every_need_is_in_the_top_k(session, embedder, tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval.settings, "hybrid_search", False)
    name = await seed(session, embedder)
    key_file = workspace_run.load_questions(write(tmp_path, key(name)))

    results = await workspace_run.evaluate(session, key_file, embedder, ks=(2, 8))

    by_id = {r.question.id: r for r in results}
    assert set(by_id) == {"both", "half"}  # `none` has no source: not scored
    assert by_id["both"].answered == {2: True, 8: True}
    assert by_id["half"].met == {2: 1, 8: 1}  # the far passage never makes the top 8 of a 15-chunk workspace
    assert by_id["half"].answered == {2: False, 8: False}


def test_the_summary_splits_seen_from_unseen_questions():
    question = workspace_run.Question(id="x", question="?", needs=[[workspace_run.Passage(paper="p", contains="c")]])
    seen = question.model_copy(update={"id": "y", "seen": True})
    results = [
        workspace_run.Result(question, answered={8: True}, met={8: 1}),
        workspace_run.Result(seen, answered={8: False}, met={8: 0}),
    ]

    assert workspace_run.summary(results, 8) == "recall@8: 0.50 (1/2) · unseen 1.00 (1/1) · seen 0.00 (0/1)"


async def test_a_passage_its_paper_does_not_hold_is_an_eval_error(session, embedder, tmp_path):
    name = await seed(session, embedder)
    path = write(tmp_path, key(name).replace("a far passage", "a passage nobody wrote"))

    with pytest.raises(workspace_run.EvalError, match="half: no chunk of 'Label, EU' holds 'a passage nobody wrote'"):
        await workspace_run.evaluate(session, workspace_run.load_questions(path), embedder)


async def test_an_unknown_workspace_is_an_eval_error(session, embedder, tmp_path):
    path = write(tmp_path, key("No such workspace"))

    with pytest.raises(workspace_run.EvalError, match="workspace 'No such workspace' not found"):
        await workspace_run.evaluate(session, workspace_run.load_questions(path), embedder)


def test_an_empty_need_is_a_malformed_file(tmp_path):
    path = write(tmp_path, 'workspace: w\nquestions:\n  - {id: a, question: "?", needs: [[]]}\n')

    with pytest.raises(workspace_run.EvalError):
        workspace_run.load_questions(path)


def test_the_shipped_key_loads_and_scores_17_of_its_20_questions():
    key_file = workspace_run.load_questions(workspace_run.QUESTIONS)

    assert len(key_file.questions) == 20
    assert sum(1 for q in key_file.questions if q.needs) == 17
    assert sorted(q.id for q in key_file.questions if q.seen) == ["q02", "q05", "q06", "q09"]


async def test_check_key_validates_without_searching(session, embedder, tmp_path):
    name = await seed(session, embedder)
    key_file = workspace_run.load_questions(write(tmp_path, key(name)))

    message = await workspace_run.check_key(session, key_file)

    assert message == "key ok: 2 scored questions, 4 passages, all in their papers"
    assert embedder.calls == []  # nothing was searched
