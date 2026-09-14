import pytest
from conftest import unit_vector

from app.models import Chunk, Paper
from evals import run

pytestmark = pytest.mark.anyio

QUESTIONS = """
questions:
  - paper: eval fixture
    question: When are self-attention layers faster?
    expected:
      - {page: 3, contains: "SELF-ATTENTION   layers are faster"}
  - paper: eval fixture
    question: Where is the faster claim made?
    expected:
      - {page: 9, contains: "self-attention layers are faster"}
"""


async def seed_paper(session, embedder):
    """Ten chunks; the first question embeds exactly onto the page-3 chunk that holds both phrases."""
    paper = Paper(title="Eval Fixture Paper", file_path="/nonexistent.pdf", status="ready")
    session.add(paper)
    await session.flush()
    texts = [f"filler chunk {i}" for i in range(10)]
    texts[2] = "In short, self-attention layers are faster than recurrent ones."
    session.add_all(
        Chunk(paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[1, 2, 3, 4]], text=text,
              embedding=unit_vector(text), embed_model="test", strategy_ver=1)
        for i, text in enumerate(texts)
    )
    await session.commit()
    embedder.vectors["search_query: When are self-attention layers faster?"] = unit_vector(texts[2])


async def test_recall_counts_page_and_phrase_hits(session, embedder, tmp_path):
    await seed_paper(session, embedder)
    path = tmp_path / "questions.yaml"
    path.write_text(QUESTIONS)
    questions = run.load_questions(path)

    missed = await run.evaluate(session, questions, embedder)

    # The second question's phrase is retrieved, but on page 3, not the expected page 9.
    assert {k: [q.question for q in misses] for k, misses in missed.items()} == {
        4: ["Where is the faster claim made?"],
        8: ["Where is the faster claim made?"],
    }
    assert [calls[0] for calls, _ in embedder.calls] == [
        "search_query: When are self-attention layers faster?",
        "search_query: Where is the faster claim made?",
    ]


async def test_unknown_paper_is_an_eval_error(session, embedder, tmp_path):
    await seed_paper(session, embedder)
    path = tmp_path / "questions.yaml"
    path.write_text(QUESTIONS.replace("paper: eval fixture", "paper: no such paper"))

    with pytest.raises(run.EvalError, match="'no such paper' matches 0 papers"):
        await run.evaluate(session, run.load_questions(path), embedder)


async def test_malformed_questions_file_exits_2(tmp_path, capsys):
    path = tmp_path / "questions.yaml"
    path.write_text("questions:\n  - paper: x\n    question: no expected pages\n")

    assert await run.main(["--questions", str(path)]) == 2
    assert "expected" in capsys.readouterr().err
