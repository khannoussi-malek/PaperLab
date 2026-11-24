"""M8.5 Ask each paper: each paper of a workspace read on its own (a record per paper), then one answer from the
records. Fake models only."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

import pytest
from conftest import unit_vector
from sqlalchemy import select, text
from test_retrieval import add_texts, make_workspace

from app.core.chat import claims, each_paper
from app.models import LLMOutput, Paper
from app.providers.base import LLMUnavailable

pytestmark = pytest.mark.anyio

QUESTION = "How does each paper measure adherence?"


class ScriptedLLM:
    """Answers each paper-reading call from `replies` by the paper title found in the prompt; records peak
    concurrency."""

    model = "scripted"
    connection_name = "Scripted"
    host = "local"

    def __init__(self, replies: dict[str, str] | None = None, default: str | None = None, delay: float = 0.0):
        self.replies = replies or {}
        self.default = default or json.dumps({"status": "found", "answer": "It does.", "cites": ["P1"]})
        self.delay = delay
        self.calls: list[str] = []
        self.running = self.peak = 0

    async def stream(self, system: str, prompt: str):
        self.calls.append(prompt)
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await asyncio.sleep(self.delay)
            reply = next((r for title, r in self.replies.items() if f"Paper: {title}\n" in prompt), self.default)
            yield reply
        finally:
            self.running -= 1


@pytest.fixture
def shared(session, monkeypatch):
    """Records are written in fresh sessions; in tests, the rolled-back test session."""

    @asynccontextmanager
    async def same():
        yield session

    monkeypatch.setattr(each_paper, "SessionLocal", same)
    return session


async def workspace_of(session, embedder, titles: list[str], chunks: int = 8):
    embedder.vectors[f"search_query: {QUESTION}"] = query = unit_vector(uuid.uuid4().hex)
    papers = []
    for title in titles:
        rows = await add_texts(session, query, title, [(f"{title} passage {i}", 0.1 + 0.05 * i) for i in range(chunks)])
        papers.append(await session.get(Paper, rows[0].paper_id))
    return await make_workspace(session, papers), papers


async def read(session, embedder, workspace, llm) -> list[each_paper.Reading]:
    plan = await each_paper.plan(session, workspace.id, QUESTION, model=llm.model, embedder=embedder)
    return [r async for r in each_paper.read_all(QUESTION, plan.tasks, llm)]


async def test_plan_reads_at_most_the_10_likeliest_papers_and_counts_the_rest(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, [f"Paper {i}" for i in range(12)], chunks=2)

    plan = await each_paper.plan(shared, workspace.id, QUESTION, model="m", embedder=embedder)

    assert len(plan.tasks) == 10 and plan.papers_total == 12


async def test_each_paper_gets_six_passages_from_itself_only(shared, embedder):
    workspace, papers = await workspace_of(shared, embedder, ["Alpha", "Beta"])

    plan = await each_paper.plan(shared, workspace.id, QUESTION, model="m", embedder=embedder)

    for task in plan.tasks:
        assert len(task.passages) == each_paper.PASSAGES == 6
        assert {p.paper_id for p in task.passages} == {task.paper.id}


async def test_a_found_record_keeps_only_cites_among_its_six_passages(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    llm = ScriptedLLM(default=json.dumps({"status": "found", "answer": "Pill counts.", "cites": ["P2", "P7", "C2"]}))

    [reading] = await read(shared, embedder, workspace, llm)

    assert reading.status == "found" and reading.answer == "Pill counts."
    assert [c.text for c in reading.cited] == ["Alpha passage 1"]
    assert reading.low_confidence is False


async def test_found_with_no_valid_cite_is_low_confidence(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    llm = ScriptedLLM(default=json.dumps({"status": "found", "answer": "Somehow.", "cites": ["P9"]}))

    [reading] = await read(shared, embedder, workspace, llm)

    assert reading.status == "found" and reading.cited == [] and reading.low_confidence is True


async def test_an_absent_record_cites_nothing(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    llm = ScriptedLLM(default=json.dumps({"status": "absent", "answer": "Not reported.", "cites": ["P1"]}))

    [reading] = await read(shared, embedder, workspace, llm)

    assert reading.status == "absent" and reading.cited == []


async def test_a_paper_without_text_is_no_text_without_a_call(shared, embedder):
    workspace, papers = await workspace_of(shared, embedder, ["Alpha"])
    bare = Paper(title="Metadata only", status="ready")
    shared.add(bare)
    await shared.flush()
    await shared.execute(
        text("INSERT INTO workspace_papers (workspace_id, paper_id) VALUES (:w, :p)"), {"w": workspace.id, "p": bare.id}
    )
    llm = ScriptedLLM()

    readings = {r.label: r for r in await read(shared, embedder, workspace, llm)}

    assert readings["Metadata only"].status == "no_text" and readings["Metadata only"].output_id is None
    assert len(llm.calls) == 1  # Alpha only


async def test_two_invalid_replies_make_a_model_error_record_and_the_run_goes_on(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha", "Beta"])
    llm = ScriptedLLM(replies={"Alpha": "not json"})

    readings = {r.label: r.status for r in await read(shared, embedder, workspace, llm)}

    assert readings == {"Alpha": "model_error", "Beta": "found"}


async def test_an_unreachable_model_after_retries_is_a_model_error_record(shared, embedder, monkeypatch):
    async def no_wait(seconds):
        pass

    monkeypatch.setattr(claims, "sleep", no_wait)
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])

    class Down(ScriptedLLM):
        async def stream(self, system, prompt):
            raise LLMUnavailable("Can't reach the model")
            yield ""

    [reading] = await read(shared, embedder, workspace, Down())

    assert reading.status == "model_error" and reading.output_id is None


async def test_a_record_is_saved_as_a_paper_reading_output(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    llm = ScriptedLLM(default=json.dumps({"status": "found", "answer": "Pill counts.", "cites": ["P1", "P3"]}))

    [reading] = await read(shared, embedder, workspace, llm)

    row = await shared.get(LLMOutput, reading.output_id)
    assert row.kind == "paper_reading" and row.question == QUESTION and row.prompt_version == 1
    assert len(row.source_chunks) == 6 and row.cited_chunks == [c.id for c in reading.cited]
    assert json.loads(row.content) == {"status": "found", "answer": "Pill counts.", "cites": ["P1", "P3"]}


async def test_the_same_question_again_reuses_the_record(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    llm = ScriptedLLM()
    [first] = await read(shared, embedder, workspace, llm)

    [again] = await read(shared, embedder, workspace, llm)

    assert len(llm.calls) == 1
    assert again.cached is True and again.output_id == first.output_id
    assert [c.id for c in again.cited] == [c.id for c in first.cited]


async def test_another_model_or_a_replaced_chunk_misses_the_cache(shared, embedder):
    workspace, papers = await workspace_of(shared, embedder, ["Alpha"])
    await read(shared, embedder, workspace, ScriptedLLM())

    other = ScriptedLLM()
    other.model = "another"
    await read(shared, embedder, workspace, other)
    mine = select(LLMOutput).where(LLMOutput.kind == "paper_reading", LLMOutput.paper_id == papers[0].id)
    row = (await shared.scalars(mine)).first()
    await shared.execute(text("DELETE FROM chunks WHERE id = :id"), {"id": row.source_chunks[0]})
    again = ScriptedLLM()
    await read(shared, embedder, workspace, again)

    assert len(other.calls) == 1 and len(again.calls) == 1


async def test_a_paper_deleted_before_it_is_read_is_skipped(shared, embedder):
    workspace, papers = await workspace_of(shared, embedder, ["Alpha", "Beta"])
    plan = await each_paper.plan(shared, workspace.id, QUESTION, model="scripted", embedder=embedder)
    await shared.delete(papers[0])
    await shared.flush()

    readings = [r async for r in each_paper.read_all(QUESTION, plan.tasks, ScriptedLLM())]

    assert [r.label for r in readings] == ["Beta"]


async def test_read_all_never_runs_more_than_two_at_once(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, [f"Paper {i}" for i in range(5)], chunks=6)
    llm = ScriptedLLM(delay=0.05)

    readings = await read(shared, embedder, workspace, llm)

    assert len(readings) == 5 and llm.peak == each_paper.MAP_CONCURRENCY == 2


async def test_the_offline_fake_model_finds_every_paper_from_its_first_passage(shared, embedder):
    """What the E2E stack (LLM_PROVIDER=fake) answers."""
    from app.providers.llm_fake import FakeLLM  # noqa: PLC0415

    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])

    [reading] = await read(shared, embedder, workspace, FakeLLM())

    assert reading.status == "found" and [c.text for c in reading.cited] == ["Alpha passage 0"]


# Task 2: one answer from the records.

def found(title: str, cites: list[str]) -> str:
    return json.dumps({"status": "found", "answer": f"{title} counts pills.", "cites": cites})


async def reduced(session, embedder, titles, replies, skill=None):
    workspace, _ = await workspace_of(session, embedder, titles)
    the_plan = await each_paper.plan(session, workspace.id, QUESTION, model="scripted", embedder=embedder, skill=skill)
    readings = [r async for r in each_paper.read_all(QUESTION, the_plan.tasks, ScriptedLLM(replies=replies))]
    return the_plan, readings, each_paper.reduce_prepared(the_plan, readings)


async def test_sources_are_the_found_records_cites_in_paper_order(shared, embedder):
    absent = json.dumps({"status": "absent", "answer": "Not reported.", "cites": []})
    the_plan, _, prepared = await reduced(
        shared, embedder, ["Alpha", "Beta", "Gamma"],
        {"Alpha": found("Alpha", ["P2", "P1"]), "Beta": absent, "Gamma": found("Gamma", ["P1"])},
    )

    order = [t.paper.title for t in the_plan.tasks if t.paper.title != "Beta"]
    expected = {"Alpha": ["Alpha passage 1", "Alpha passage 0"], "Gamma": ["Gamma passage 0"]}
    assert [s.text for s in prepared.sources] == [text for title in order for text in expected[title]]
    assert prepared.prompt_version == each_paper.EACH_PAPER_PROMPT_VERSION == 1
    assert prepared.whole_paper is False and prepared.notes == []


async def test_the_prompt_rewrites_each_records_cites_to_its_c_labels(shared, embedder):
    _, _, prepared = await reduced(shared, embedder, ["Alpha"], {"Alpha": found("Alpha", ["P2"])})

    assert "[C1]" in prepared.prompt and "[P2]" not in prepared.prompt
    assert "Alpha counts pills. [C1]" in prepared.prompt


async def test_the_prompt_names_every_paper_that_does_not_cover_it(shared, embedder):
    absent = json.dumps({"status": "absent", "answer": "Not reported.", "cites": []})
    replies = {"Alpha": found("Alpha", ["P1"]), "Beta": absent}
    _, _, prepared = await reduced(shared, embedder, ["Alpha", "Beta"], replies)

    assert "Not covered by: Beta" in prepared.prompt


async def test_the_prompt_says_how_many_papers_were_not_read(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, [f"Paper {i}" for i in range(12)], chunks=2)
    the_plan = await each_paper.plan(shared, workspace.id, QUESTION, model="scripted", embedder=embedder)
    readings = [r async for r in each_paper.read_all(QUESTION, the_plan.tasks, ScriptedLLM())]

    prepared = each_paper.reduce_prepared(the_plan, readings)

    assert "Not read: 2 of 12 papers" in prepared.prompt


async def test_a_skill_shapes_the_answer_not_the_reading(shared, embedder):
    from app.core.platform import skills  # noqa: PLC0415

    skill = skills.SkillView(
        id="custom:x", label="Table", description="", scope="workspace", instructions="Answer as a table.",
        version=1, is_listed=True, is_paper_default=False, is_workspace_default=False, state="custom", lens="full",
    )
    llm = ScriptedLLM()
    workspace, _ = await workspace_of(shared, embedder, ["Alpha"])
    the_plan = await each_paper.plan(shared, workspace.id, QUESTION, model="scripted", embedder=embedder, skill=skill)
    readings = [r async for r in each_paper.read_all(QUESTION, the_plan.tasks, llm)]

    prepared = each_paper.reduce_prepared(the_plan, readings)

    assert prepared.system == skills.compose(each_paper.EACH_PAPER_SYSTEM, skill)
    assert "Answer as a table." not in llm.calls[0]
    assert prepared.skill_label == "Table"


async def test_the_saved_answer_keeps_its_readings_and_lists_them_again(shared, embedder):
    from app.core.chat import chat  # noqa: PLC0415

    the_plan, readings, prepared = await reduced(shared, embedder, ["Alpha", "Beta"], {})
    scope = chat.Scope(workspace_id=the_plan.workspace_id)

    output_id = await chat.save_answer(shared, scope, QUESTION, prepared, "Both count pills [C1][C2].", "m", "c")

    [answer] = await chat.list_answers(shared, scope)
    assert answer.output.id == output_id
    in_paper_order = [r.output_id for t in the_plan.tasks for r in readings if r.paper_id == t.paper.id]
    assert answer.output.readings == prepared.readings == in_paper_order
    assert [r.id for r in answer.readings] == in_paper_order


# Review fixes.

async def test_a_record_read_from_other_passages_is_not_reused(shared, embedder):
    """Same question, paper and model, but the passages changed (a skill's lens, a new nearer chunk): read again."""
    workspace, papers = await workspace_of(shared, embedder, ["Alpha"])
    await read(shared, embedder, workspace, ScriptedLLM())
    query = embedder.vectors[f"search_query: {QUESTION}"]
    from test_retrieval import at_spread  # noqa: PLC0415

    from app.models import Chunk  # noqa: PLC0415

    shared.add(Chunk(paper_id=papers[0].id, ordinal=99, page=9, bbox=[[1, 2, 3, 4]], text="Alpha nearest passage",
                     embedding=at_spread(query, 0.01), embed_model="test", strategy_ver=1))
    await shared.flush()
    again = ScriptedLLM()

    [reading] = await read(shared, embedder, workspace, again)

    assert len(again.calls) == 1 and reading.cached is False


async def test_an_unexpected_error_for_one_paper_is_its_model_error_and_the_run_goes_on(shared, embedder):
    workspace, _ = await workspace_of(shared, embedder, ["Alpha", "Beta"])

    class Broken(ScriptedLLM):
        async def stream(self, system, prompt):
            if "Paper: Alpha\n" in prompt:
                raise ValueError("a bug in a provider")
            async for token in super().stream(system, prompt):
                yield token

    readings = {r.label: r.status for r in await read(shared, embedder, workspace, Broken())}

    assert readings == {"Alpha": "model_error", "Beta": "found"}


async def test_a_records_own_markers_never_reach_the_answers_prompt(shared, embedder):
    reply = json.dumps({"status": "found", "answer": "Pill counts [P2] as in [C1].", "cites": ["P1"]})
    _, _, prepared = await reduced(shared, embedder, ["Alpha"], {"Alpha": reply})

    assert "Pill counts as in. [C1]" in prepared.prompt
    assert "[P2]" not in prepared.prompt
