import json
import uuid
from contextlib import asynccontextmanager

import pytest
from conftest import TEST_DATABASE_URL, unit_vector
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import chat, prompts
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, Note, Paper, Workspace
from app.providers import llm as llm_provider
from evals import answers
from evals.run import Expected

pytestmark = pytest.mark.anyio

CASES = """
cases:
  - id: layers
    kind: fact
    paper: answers fixture
    question: How many layers does the encoder have?
    points: [["6 layers", "six layers"]]
    evidence: [{page: 1, contains: "a stack of 6 identical layers"}]
  - id: tool
    kind: notes
    paper: answers fixture
    question: Which tool does my note name?
    points: [["kestrel"]]
    note: {page: 1, quote: "a stack of 6 identical layers", body: "We rebuilt this in Kestrel."}
"""

PAPER_NOTES = """
paper_notes:
  - paper: answers fixture
    notes:
      - {page: 1, quote: "a stack of 6 identical layers", body: "Compare with BERT's encoder."}
      - {page: 2, quote: "Decoder text", body: "The decoder mirrors the encoder.", provenance: llm}
"""

WRITE_NOTES = """
  - id: notes-paper
    kind: write_notes
    paper: answers fixture
    question: Create notes on the encoder.
    points: [["layers"]]
  - id: notes-workspace
    kind: write_notes
    scope: workspace
    paper: answers fixture
    question: Write notes comparing these papers.
    points: [["layers"]]
"""
FOLLOW_UP = """
  - id: next
    kind: followup
    paper: answers fixture
    before: What is the encoder?
    question: And how many layers?
    points: [["6 layers"]]
"""


def chunk(page: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(id=uuid.uuid4(), paper_id=uuid.uuid4(), page=page, section=None, bbox=[], text=text)


def write_cases(tmp_path, text: str = CASES):
    path = tmp_path / "answers.yaml"
    path.write_text(text)
    return answers.load_cases(path)


def test_mentions_matches_whole_words_ignoring_case_spacing_and_thousands_separators():
    assert answers.mentions("It studied 20574   Sessions.", "20,574 sessions")
    assert answers.mentions("38.33% of episodes", "38.33")
    assert answers.mentions("CLI agents differ", "cli")
    assert not answers.mentions("the client differs", "cli")
    assert not answers.mentions("138.33% of episodes", "38.33")


def test_an_answer_is_correct_when_it_hits_enough_points(tmp_path):
    case = answers.Case(
        id="summary", kind="overview", paper="p", question="q", need=2,
        points=[["transformer"], ["bleu", "translation"], ["parallel"]],
    )
    assert answers.points_hit("The Transformer improves translation.", case.points) == 2
    assert answers.is_correct("The Transformer improves translation.", case)
    assert not answers.is_correct("The Transformer is new.", case)
    fact = write_cases(tmp_path)[0]
    assert fact.required == 1  # every point, when need isn't given


@pytest.mark.parametrize(
    "case, problem",
    [
        ("{id: a, kind: fact, paper: p, question: q, points: [[x]]}", "fact needs evidence"),
        ("{id: a, kind: followup, paper: p, question: q, points: [[x]]}", "followup needs before"),
        ("{id: a, kind: notes, paper: p, question: q, points: [[x]]}", "notes needs note"),
        ("{id: a, kind: overview, paper: p, question: q, points: [[x]], need: 2}", "need is more than the 1 points"),
    ],
)
def test_a_case_must_carry_what_its_kind_needs(tmp_path, case, problem):
    with pytest.raises(answers.EvalError, match=problem):
        write_cases(tmp_path, f"cases:\n  - {case}\n")


def test_case_ids_are_unique(tmp_path):
    overview = "{id: a, kind: overview, paper: p, question: q, points: [[x]]}"
    with pytest.raises(answers.EvalError, match="duplicate case id 'a'"):
        write_cases(tmp_path, f"cases:\n  - {overview}\n  - {overview}\n")


def test_a_refusal_is_correct_when_the_answer_says_the_paper_does_not_cover_it():
    case = answers.Case(id="cost", kind="refusal", paper="p", question="What did training cost in dollars?")

    assert case.required == 1
    assert answers.is_correct("The sources do not mention the training cost.", case)
    assert answers.is_correct("That isn't specified in the paper... it is not specified.", case)
    # Phrasings qwen3:8b actually used, which the first list missed.
    assert answers.is_correct("The question cannot be answered based on the provided sources and notes.", case)
    assert answers.is_correct("There is no mention of interviews with developers.", case)
    assert not answers.is_correct("Training cost about $4,000 [C2].", case)


def test_cases_other_than_refusals_need_points(tmp_path):
    with pytest.raises(answers.EvalError, match="a: fact needs points"):
        fact = "{id: a, kind: fact, paper: p, question: q, evidence: [{page: 1, contains: x}]}"
        write_cases(tmp_path, f"cases:\n  - {fact}\n")


def test_select_cases_by_id_or_kind(tmp_path):
    cases = write_cases(tmp_path)
    assert [c.id for c in answers.select_cases(cases, only="tool", kinds=None)] == ["tool"]
    assert [c.id for c in answers.select_cases(cases, only=None, kinds="fact,notes")] == ["layers", "tool"]
    with pytest.raises(answers.EvalError, match="unknown kinds: essay"):
        answers.select_cases(cases, only=None, kinds="essay")


def test_paper_notes_load_with_human_provenance_unless_marked_ai(tmp_path):
    path = tmp_path / "answers.yaml"
    path.write_text(CASES + PAPER_NOTES)

    [block] = answers.load(path).paper_notes

    assert block.paper == "answers fixture"
    assert [(n.page, n.provenance) for n in block.notes] == [(1, "human"), (2, "llm")]


def test_grounded_needs_a_cited_passage_that_holds_the_evidence():
    sources = [chunk(1, "Alpha."), chunk(2, "The answer is   42 here.")]
    evidence = [Expected(page=2, contains="answer is 42")]
    assert answers.grounded("It is 42 [C2].", sources, evidence) is True
    assert answers.grounded("It is 42 [C1].", sources, evidence) is False
    assert answers.grounded("It is 42 [C9].", sources, evidence) is False
    assert answers.grounded("It is 42.", sources, []) is None


async def seed_paper(session, texts_by_page: dict[int, str], embedded=False) -> Paper:
    paper = Paper(title="Answers Fixture Paper", file_path="/nonexistent.pdf", status="ready")
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(paper_id=paper.id, ordinal=i, page=page, bbox=[[1, 2, 3, 4]], text=text, embed_model="test",
              strategy_ver=1, embedding=unit_vector(text) if embedded else None)
        for i, (page, text) in enumerate(texts_by_page.items())
    )
    await session.flush()
    return paper


async def test_ground_truth_must_be_on_its_page(session, tmp_path):
    paper = await seed_paper(session, {1: "The encoder is a stack of 6 identical layers.", 2: "Other text."})
    ok, _, wrong_page, missing_quote = write_cases(tmp_path, CASES + """
  - id: moved
    kind: fact
    paper: answers fixture
    question: q
    points: [["x"]]
    evidence: [{page: 2, contains: "a stack of 6 identical layers"}]
  - id: unquoted
    kind: notes
    paper: answers fixture
    question: q
    points: [["x"]]
    note: {page: 1, quote: "words that are nowhere", body: "b"}
""")

    problems = await answers.check_ground_truth(session, [ok, wrong_page, missing_quote], {"answers fixture": paper.id})

    assert problems == [
        "moved: evidence 'a stack of 6 identical layers' isn't on page 2",
        "unquoted: note quote 'words that are nowhere' isn't on page 1",
    ]
    stray = answers.PaperNotes(
        paper="answers fixture", notes=[answers.NoteFixture(page=2, quote="nowhere at all", body="b")]
    )
    assert await answers.check_ground_truth(session, [ok], {"answers fixture": paper.id}, [stray]) == [
        "answers fixture: note quote 'nowhere at all' isn't on page 2"
    ]


def row(config, case, correct, **extra):
    return {
        "label": "today", "config": config, "case": case, "kind": "fact", "repeat": 0, "correct": correct,
        "points": 4 if correct else 2, "of": 4, "grounded": correct, "citations_valid": True, "ttft": 1.0, "total": 2.0,
        "prompt_chars": 100, "first_on_paper": False, "error": None, **extra,
    }


def test_summary_gives_rates_and_leaves_out_what_the_model_knew_without_reading():
    rows = [
        row("none", "known", True, grounded=False, citations_valid=None),
        row("none", "unseen", False, grounded=False, citations_valid=None),
        row("retrieval", "known", True, ttft=1.0, first_on_paper=True),
        row("retrieval", "unseen", False, grounded=False, ttft=3.0),
        row("retrieval", "unseen", False, grounded=False, ttft=0.1, total=0.2, repeat=1),  # the same prompt, cached
        row("whole", "known", True),
        row("whole", "unseen", True),
        row("whole", "unseen", None, error="timeout"),
    ]

    by_config = {s["config"]: s for s in answers.summary(rows)}

    retrieval, whole = by_config["retrieval"], by_config["whole"]
    assert (retrieval["answers"], retrieval["correct"], retrieval["correct_unseen"]) == (3, 0.33, 0.0)
    assert (retrieval["grounded"], retrieval["coverage"]) == (0.33, 0.67)  # key points hit: 4/4, 2/4 and 2/4
    # Timings count only a question's first ask: a repeat reuses the model's cache of the identical prompt.
    assert (retrieval["median_ttft"], retrieval["median_total"], retrieval["median_ttft_first"]) == (2.0, 2.0, 1.0)
    assert (whole["answers"], whole["errors"], whole["correct"], whole["correct_unseen"]) == (2, 1, 1.0, 1.0)
    assert by_config["none"]["citations_valid"] is None
    assert "| today | whole | fact |" in answers.format_summary(answers.summary(rows))


def test_completed_skips_answers_already_written_but_retries_errors(tmp_path):
    out = tmp_path / "today.jsonl"
    out.write_text(json.dumps(row("whole", "a", True)) + "\n" + json.dumps(row("whole", "b", None, error="x")) + "\n")

    assert answers.completed(out) == {("today", "whole", "a", 0)}
    assert answers.completed(tmp_path / "missing.jsonl") == set()


def savepoints(session):
    """A scratch factory for evaluate(): each use runs in a savepoint of the test's session, rolled back after."""

    @asynccontextmanager
    async def scratch():
        savepoint = await session.begin_nested()
        try:
            yield session
        finally:
            await savepoint.rollback()

    return scratch


class ScriptedLLM:
    model = "scripted"
    connection_name = "Scripted"

    def __init__(self, text: str):
        self.text = text
        self.calls: list[tuple[str, str, int, int]] = []

    async def stream(self, system: str, prompt: str):
        self.calls.append((system, prompt, llm_provider.OLLAMA_NUM_CTX, chat.SMALL_PAPER_CHARS))
        for word in self.text.split(" "):
            yield word + " "


async def test_evaluate_scores_each_answer_once_and_never_keeps_a_notes_fixture(session, embedder, tmp_path):
    paper_id = (await seed_paper(session, {1: "The encoder is a stack of 6 identical layers.", 2: "Decoder text."})).id
    cases = write_cases(tmp_path, CASES + """
  - id: next
    kind: followup
    paper: answers fixture
    before: What is the encoder?
    question: And how many layers?
    points: [["6 layers"]]
    evidence: [{page: 1, contains: "a stack of 6 identical layers"}]
""")
    llm = ScriptedLLM("The encoder has 6 layers [C1].")
    out = tmp_path / "today.jsonl"

    async def evaluate():
        await answers.evaluate(
            cases, paper_ids={"answers fixture": paper_id}, configs=["none", "whole"], repeats=2, label="today",
            out=out, scratch=savepoints(session), llm=llm, embedder=embedder,
        )

    await evaluate()

    rows = answers.read_rows(out)
    assert [(r["config"], r["case"], r["repeat"]) for r in rows] == [
        ("none", "layers", 0),  # no-passage runs once, and never for notes or follow-ups
        ("whole", "layers", 0), ("whole", "layers", 1), ("whole", "tool", 0), ("whole", "tool", 1),
        ("whole", "next", 0), ("whole", "next", 1),
    ]
    none, whole = rows[0], rows[1]
    assert (none["sources"], none["grounded"], none["citations_valid"]) == (0, False, None)
    assert "answers fixture" in llm.calls[1][1] and "Sources" not in llm.calls[1][1]
    assert (whole["correct"], whole["grounded"], whole["citations_valid"], whole["points"], whole["of"]) == (
        True, True, True, 1, 1,
    )
    assert (whole["sources"], whole["whole_paper"], whole["first_on_paper"], rows[2]["first_on_paper"]) == (
        2, True, True, False,
    )
    assert whole["ttft"] is not None and whole["total"] >= whole["ttft"] and whole["error"] is None
    assert rows[3]["correct"] is False and rows[3]["kind"] == "notes"
    whole_calls = [c for c in llm.calls if c[2] == answers.WHOLE_NUM_CTX]
    assert len(whole_calls) == 7 and all(c[3] == answers.WHOLE_PAPER_CHARS for c in whole_calls)  # 1 warm-up + 6
    # A follow-up carries the earlier question, which is never itself asked: its answer isn't part of the context.
    assert whole_calls[-1][1].endswith("oldest first:\n- What is the encoder?\n\nQuestion: And how many layers?\n")
    assert not any(call[1].endswith("Question: What is the encoder?\n") for call in llm.calls)
    assert (llm_provider.OLLAMA_NUM_CTX, chat.SMALL_PAPER_CHARS) == (16_384, 24_000)  # restored
    kept = select(func.count()).select_from(Note).where(Note.body == "We rebuilt this in Kestrel.")
    assert await session.scalar(kept) == 0

    calls = len(llm.calls)
    await evaluate()  # a rerun only fills gaps
    assert len(answers.read_rows(out)) == 7 and len(llm.calls) == calls


async def test_rolled_back_discards_every_write():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    body = f"answers eval rollback {uuid.uuid4()}"
    try:
        async with answers.rolled_back(engine) as scratch:
            scratch.add(Note(body=body, provenance="human"))
            await scratch.commit()  # even a commit only releases a savepoint
        async with engine.connect() as connection:
            assert await connection.scalar(select(func.count()).select_from(Note).where(Note.body == body)) == 0
    finally:
        await engine.dispose()


async def test_paper_notes_join_every_question_on_their_paper_and_are_never_kept(session, embedder, tmp_path):
    paper_id = (await seed_paper(session, {1: "The encoder is a stack of 6 identical layers.", 2: "Decoder text."})).id
    path = tmp_path / "answers.yaml"
    path.write_text(CASES + PAPER_NOTES)
    loaded = answers.load(path)
    llm = ScriptedLLM("Six layers [C1].")

    await answers.evaluate(
        loaded.cases[:1], paper_ids={"answers fixture": paper_id}, configs=["retrieval"], repeats=1, label="noted",
        out=tmp_path / "noted.jsonl", scratch=savepoints(session), llm=llm, embedder=embedder,
        paper_notes=loaded.paper_notes,
    )

    [row] = answers.read_rows(tmp_path / "noted.jsonl")
    prompt = llm.calls[-1][1]
    assert row["notes"] == 2 and "(You · Answers Fixture Paper p.1)" in prompt
    assert "(AI · Answers Fixture Paper p.2)" in prompt and "— Compare with BERT's encoder." in prompt
    bodies = ["Compare with BERT's encoder.", "The decoder mirrors the encoder."]
    assert await session.scalar(select(func.count()).select_from(Note).where(Note.body.in_(bodies))) == 0


def test_rescore_updates_what_depends_only_on_the_answer_text(tmp_path):
    cases = write_cases(tmp_path, CASES + """
  - id: cost
    kind: refusal
    paper: answers fixture
    question: What did it cost?
""")
    stale = row("whole", "cost", False, kind="refusal", points=0, of=1, need=1, grounded=None,
                content="The question cannot be answered based on the provided sources.")
    unknown = row("whole", "gone", True, content="whatever")
    out = tmp_path / "old.jsonl"
    out.write_text(json.dumps(stale) + "\n" + json.dumps(unknown) + "\n")

    changed = answers.rescore(out, cases)

    rescored, kept = answers.read_rows(out)
    assert changed == 1
    assert (rescored["correct"], rescored["points"], rescored["grounded"]) == (True, 1, None)
    assert kept == unknown  # a case no longer in the file stays as it was


def test_blocks_are_right_when_notes_are_asked_for_and_absent_otherwise():
    two = ":::note\nSix layers [C1].\n:::\n:::note\nThe decoder mirrors it [C2].\n:::"

    assert answers.blocks_right(two, "write_notes", 2) is True
    assert answers.blocks_right(two, "write_notes", 1) is False  # [C2] is not one of the sources
    assert answers.blocks_right(":::note\n\n:::", "write_notes", 1) is False  # an empty block
    assert answers.blocks_right("Six layers [C1].", "write_notes", 1) is False  # no block at all
    assert answers.blocks_right("Six layers [C1].", "fact", 1) is True
    assert answers.blocks_right(two, "fact", 2) is False


def test_previous_prompts_ask_as_chat_did_before_note_blocks_and_are_put_back():
    def current():
        return chat.SYSTEM_PROMPT, chat.PROMPT_TEMPLATE, chat.WORKSPACE_SYSTEM_PROMPT, chat.WORKSPACE_PROMPT_TEMPLATE

    before = current()
    with answers.prompt_set("previous"):
        assert chat.SYSTEM_PROMPT + chat.PROMPT_TEMPLATE == prompts.load("chat", 2).replace(chat.PROMPT_MARKER, "")
        old_workspace = prompts.load("chat_workspace", 1).replace(chat.PROMPT_MARKER, "")
        assert chat.WORKSPACE_SYSTEM_PROMPT + chat.WORKSPACE_PROMPT_TEMPLATE == old_workspace
        assert ":::note" not in chat.SYSTEM_PROMPT + chat.WORKSPACE_SYSTEM_PROMPT
    with answers.prompt_set("current"):
        assert current() == before
    assert current() == before and ":::note" in chat.SYSTEM_PROMPT and ":::note" in chat.WORKSPACE_SYSTEM_PROMPT


async def test_the_workspace_config_asks_across_the_eval_papers_skips_follow_ups_and_scores_blocks(
    session, embedder, tmp_path
):
    run = uuid.uuid4().hex  # unique vectors per run (D37)
    texts = {1: f"{run} The encoder is a stack of 6 identical layers.", 2: f"{run} Decoder text."}
    paper_id = (await seed_paper(session, texts, embedded=True)).id
    cases = write_cases(tmp_path, CASES + FOLLOW_UP + WRITE_NOTES)
    llm = ScriptedLLM(":::note\nSix layers [C1].\n:::")
    out = tmp_path / "workspace.jsonl"

    await answers.evaluate(
        cases, paper_ids={"answers fixture": paper_id}, configs=["workspace", "retrieval"], repeats=1, label="ws",
        out=out, scratch=savepoints(session), llm=llm, embedder=embedder,
    )

    rows = answers.read_rows(out)
    assert [(r["config"], r["case"]) for r in rows] == [
        ("workspace", "layers"), ("workspace", "tool"), ("workspace", "notes-paper"), ("workspace", "notes-workspace"),
        ("retrieval", "layers"), ("retrieval", "tool"), ("retrieval", "next"), ("retrieval", "notes-paper"),
    ]  # fmt: skip
    assert [call[0] for call in llm.calls[1:5]] == [chat.WORKSPACE_SYSTEM_PROMPT] * 4  # calls[0] is the warm-up
    assert {(r["case"], r["blocks"], r["blocks_right"]) for r in rows if r["config"] == "workspace"} == {
        ("layers", 1, False), ("tool", 1, False), ("notes-paper", 1, True), ("notes-workspace", 1, True),
    }  # fmt: skip
    left = select(func.count()).select_from(Workspace).where(Workspace.name.like("answers eval %"))
    assert await session.scalar(left) == 0  # the scratch workspaces were rolled back
