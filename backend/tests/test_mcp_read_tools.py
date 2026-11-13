"""M28: the MCP read tools paper_references, list_datasets, get_dataset and saved_answers, through an in-process client
against the real test database (the test's rolled-back transaction)."""

import uuid

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from pdf_papers import chunked_paper
from sqlalchemy import delete

from app.core import chat, datasets, references, workspaces
from app.core.datasets import CellIn, ColumnIn, GridIn, RowIn
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, ExternalRef, LLMOutput, Note, NoteEmbedding, Paper, PaperSources, paper_references

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)
READER_DOI = f"10.5555/m28-reader-{RUN}"


@pytest.fixture
async def library(session):
    """The dev database may hold the owner's references and notes: hide them for these tests (rolled back)."""
    for model in (paper_references, NoteEmbedding, ExternalRef, Note, PaperSources):
        await session.execute(delete(model))
    return session


async def reader(session, **fields) -> Paper:
    fields.setdefault("references_state", "none")  # the server default, which an unflushed Paper doesn't carry
    paper = Paper(title="Reader", file_path="/nonexistent.pdf", doi=READER_DOI, **fields)
    session.add(paper)
    await session.flush()
    return paper


def grid(*rows: tuple[str, ...]) -> GridIn:
    return GridIn(
        columns=[ColumnIn(id=None, name="Model", unit=None), ColumnIn(id=None, name="F1", unit="%")],
        rows=[RowIn(id=None, cells=[CellIn(raw=text) for text in row]) for row in rows],
    )


# --- paper_references --------------------------------------------------------------------------------------------


async def test_references_answer_with_their_state_summary_and_library_marks(library):
    paper = await reader(library, references_state="ready")
    in_library = await add_library_copy(library, doi=f"10.5555/m28-held-{RUN}")
    held = ExternalRef(
        title="Held reference", authors=["A. Writer"], year=2019, venue="Journal X", doi=in_library.doi,
        cited_by_count=7, pdf_urls=[],
    )  # fmt: skip
    free = ExternalRef(title="Free reference", doi=f"10.5555/m28-free-{RUN}", pdf_urls=["https://pdf.example/a.pdf"])
    library.add_all([held, free])
    await library.flush()
    await library.execute(
        paper_references.insert(),
        [
            {"paper_id": paper.id, "ref_id": held.id, "direction": "cites", "position": 0},
            {"paper_id": paper.id, "ref_id": free.id, "direction": "cites", "position": 1},
        ],
    )
    await library.commit()

    answer = result(await call("paper_references", paper_id=str(paper.id)))

    assert (answer["state"], answer["error"], answer["direction"]) == ("ready", None, "references")
    assert answer["summary"] == {"cited_by_3plus": 0, "with_pdf": 1}
    assert (answer["total"], answer["truncated"]) == (2, False)
    # ranked as references.RANK: the free PDF first, the held one (equal co-citation) after
    assert [row["title"] for row in answer["rows"]] == ["Free reference", "Held reference"]
    assert answer["rows"][1] == {
        "title": "Held reference", "authors": ["A. Writer"], "year": 2019, "venue": "Journal X",
        "doi": in_library.doi, "arxiv_id": None, "in_library": True, "library_paper_id": str(in_library.id),
        "cocitation": 1, "cited_by_count": 7,
    }  # fmt: skip
    assert (answer["rows"][0]["in_library"], answer["rows"][0]["library_paper_id"]) == (False, None)
    assert answer["note"] is None


async def add_library_copy(session, doi: str) -> Paper:
    copy = Paper(title="Held in the library", file_path="/nonexistent.pdf", doi=doi)
    session.add(copy)
    await session.flush()
    return copy


async def test_citing_works_are_the_cited_by_rows(library):
    paper = await reader(library, references_state="ready")
    citer = ExternalRef(title="A citing work", cited_by_count=3)
    library.add(citer)
    await library.flush()
    await library.execute(
        paper_references.insert(), [{"paper_id": paper.id, "ref_id": citer.id, "direction": "cited_by", "position": 0}]
    )
    await library.commit()

    cites = result(await call("paper_references", paper_id=str(paper.id)))
    citing = result(await call("paper_references", paper_id=str(paper.id), direction="citing"))

    assert (cites["total"], cites["rows"]) == (0, [])
    assert (citing["direction"], [row["title"] for row in citing["rows"]]) == ("citing", ["A citing work"])


async def test_a_listing_never_fetched_says_so_and_makes_no_network_call(library, monkeypatch):
    paper = await reader(library)  # references_state defaults to "none"

    async def no_fetch(*_args, **_kwargs):
        raise AssertionError("paper_references must never fetch")

    monkeypatch.setattr(references, "fetch", no_fetch)

    answer = result(await call("paper_references", paper_id=str(paper.id)))

    assert (answer["state"], answer["rows"], answer["total"], answer["truncated"]) == ("none", [], 0, False)
    assert answer["note"] == "Not fetched yet: the owner can fetch them from the paper's References tab."


async def test_a_failed_fetch_says_why_and_makes_no_network_call(library, monkeypatch):
    paper = await reader(library, references_state="failed", references_error="Fetching references failed. Try again.")

    async def no_fetch(*_args, **_kwargs):
        raise AssertionError("paper_references must never fetch")

    monkeypatch.setattr(references, "fetch", no_fetch)

    answer = result(await call("paper_references", paper_id=str(paper.id)))

    assert (answer["state"], answer["error"], answer["rows"]) == (
        "failed",
        "Fetching references failed. Try again.",
        [],
    )
    assert answer["note"] is None  # the error says why; the note is only for a listing never fetched


async def test_references_cap_at_100_rows_and_say_so(library):
    paper = await reader(library, references_state="ready")
    refs = [ExternalRef(title=f"Reference {i:03d}", cited_by_count=i) for i in range(101)]
    library.add_all(refs)
    await library.flush()
    await library.execute(
        paper_references.insert(),
        [{"paper_id": paper.id, "ref_id": ref.id, "direction": "cites", "position": i} for i, ref in enumerate(refs)],
    )
    await library.commit()

    answer = result(await call("paper_references", paper_id=str(paper.id)))

    assert (answer["total"], answer["truncated"], len(answer["rows"])) == (101, True, 100)


async def test_an_unknown_paper_is_a_recoverable_error(library):
    unknown = uuid.uuid4()

    answer = await call("paper_references", paper_id=str(unknown))

    assert answer.is_error and answer.structured_content == {"error": "unknown_paper"}


async def test_an_unknown_direction_is_refused_by_argument_validation(library):
    paper = await reader(library)

    answer = await call("paper_references", paper_id=str(paper.id), direction="sideways")

    assert answer.is_error and "direction" in answer.content[0].text


# --- list_datasets and get_dataset -------------------------------------------------------------------------------


async def test_list_datasets_by_paper_or_all_with_titles_and_counts(session):
    paper = await reader(session)
    table = await datasets.create_dataset(
        session, f"Table {RUN}", "table", grid(("a", "1"), ("b", "2")), paper_id=paper.id, page=2,
        region=(1.0, 2.0, 300.0, 400.0),
    )  # fmt: skip
    own = await datasets.create_dataset(session, f"Mine {RUN}", "user", grid(("c", "3")))
    await session.commit()

    listed = result(await call("list_datasets", paper_id=str(paper.id)))
    everything = result(await call("list_datasets"))

    assert listed == [{
        "id": str(table.id), "name": f"Table {RUN}", "kind": "table", "paper_id": str(paper.id),
        "paper_title": "Reader", "page": 2, "row_count": 2, "column_count": 2,
        "created_at": listed[0]["created_at"],
    }]  # fmt: skip
    assert {row["id"] for row in everything} >= {str(table.id), str(own.id)}


async def test_get_dataset_returns_columns_cells_and_charts(session):
    paper = await reader(session)
    table = await datasets.create_dataset(
        session, f"Scores {RUN}", "table", grid(("Alpha", "91.2")), paper_id=paper.id, page=3,
        region=(1.0, 2.0, 300.0, 400.0),
    )  # fmt: skip
    await session.commit()

    view = result(await call("get_dataset", dataset_id=str(table.id)))

    assert (view["id"], view["name"], view["kind"], view["page"]) == (str(table.id), f"Scores {RUN}", "table", 3)
    assert view["columns"] == [{"name": "Model", "unit": None}, {"name": "F1", "unit": "%"}]
    cells = view["rows"][0]
    assert [(c["raw"], c["value"], c["origin"]) for c in cells] == [("Alpha", None, "human"), ("91.2", 91.2, "human")]
    assert (view["truncated"], view["charts"]) == (False, [])


async def test_get_dataset_caps_at_200_rows(session):
    table = await datasets.create_dataset(
        session, f"Long {RUN}", "user", grid(*[(f"r{i}", str(i)) for i in range(201)])
    )
    await session.commit()

    view = result(await call("get_dataset", dataset_id=str(table.id)))

    assert (len(view["rows"]), view["truncated"]) == (200, True)


async def test_unknown_dataset_and_paper_are_recoverable_errors(session):
    missing_dataset = await call("get_dataset", dataset_id=str(uuid.uuid4()))
    missing_paper = await call("list_datasets", paper_id=str(uuid.uuid4()))

    assert missing_dataset.is_error and missing_dataset.structured_content == {"error": "unknown_dataset"}
    assert missing_paper.is_error and missing_paper.structured_content == {"error": "unknown_paper"}


# --- saved_answers -----------------------------------------------------------------------------------------------


async def answer_on(session, scope: chat.Scope | uuid.UUID, question: str, sources=(), skill_label=None) -> LLMOutput:
    prepared = chat.Prepared(
        sources=list(sources), system="", prompt="", whole_paper=True, skill_label=skill_label
    )  # fmt: skip
    output_id = await chat.save_answer(
        session, scope, question, prepared, f"Answer to {question} [C1].", "qwen3:8b", "Ollama"
    )
    return await session.get(LLMOutput, output_id)  # fmt: skip


async def test_saved_answers_come_newest_first_marked_ai_with_their_sources(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Answered paper")
    sources = await chat.chunk_sources(session, Chunk.paper_id == paper.id)
    await answer_on(session, paper.id, "First?", sources, skill_label="Critic")
    await answer_on(session, paper.id, "Second?")
    await session.commit()

    answer = result(await call("saved_answers", paper_id=str(paper.id)))

    assert (answer["total"], [a["question"] for a in answer["answers"]]) == (2, ["Second?", "First?"])
    newest, first = answer["answers"]
    assert (newest["ai"], newest["model"], newest["skill_label"], newest["sources"]) == (True, "qwen3:8b", None, [])
    assert newest["content"] == "Answer to Second? [C1]."
    assert newest["notes_used"] is None
    assert first["skill_label"] == "Critic"
    assert first["sources"] == [
        {"label": f"C{i}", "paper_id": str(paper.id), "page": s.page, "section": s.section}
        for i, s in enumerate(sources, start=1)
    ]
    assert first["sources_missing"] == 0


async def test_saved_answers_hide_a_sources_page_for_an_abstract(session):
    paper = Paper(title="Abstract only", file_path=None)
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(paper_id=paper.id, ordinal=0, page=0, bbox=[], text="An abstract.", embed_model="test", strategy_ver=1)
    )
    await session.flush()
    abstract = await chat.chunk_sources(session, Chunk.paper_id == paper.id)
    await answer_on(session, paper.id, "About?", abstract)
    await session.commit()

    answer = result(await call("saved_answers", paper_id=str(paper.id)))

    assert answer["answers"][0]["sources"][0]["page"] is None


async def test_a_source_a_reingest_replaced_is_skipped_and_counted(session, tmp_path):
    paper, chunks, _ = await chunked_paper(session, tmp_path, title="Re-ingested")
    sources = await chat.chunk_sources(session, Chunk.paper_id == paper.id)
    gone = RetrievedChunk(id=uuid.uuid4(), paper_id=paper.id, page=1, section=None, bbox=[], text="gone")
    await answer_on(session, paper.id, "Mixed?", [gone, *sources])
    await session.commit()

    answer = result(await call("saved_answers", paper_id=str(paper.id)))

    shown = answer["answers"][0]
    assert shown["sources_missing"] == 1
    assert [s["label"] for s in shown["sources"]] == [f"C{i}" for i in range(2, len(sources) + 2)]


async def test_saved_answers_in_a_workspace_by_exact_name(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Workspace paper")
    name = f"M28 answers {RUN}"
    workspace = await workspaces.create(session, name)
    await workspaces.add_paper(session, workspace.id, paper.id)
    await answer_on(session, chat.Scope(workspace_id=workspace.id), "In the workspace?")
    await session.commit()

    answer = result(await call("saved_answers", workspace=name))

    assert [a["question"] for a in answer["answers"]] == ["In the workspace?"]
    wrong_case = await call("saved_answers", workspace=name.upper())
    assert wrong_case.is_error and wrong_case.structured_content["error"] == "unknown_workspace"


async def test_saved_answers_page_twenty_at_a_time_with_an_offset(session):
    paper = await reader(session)
    for i in range(21):
        await answer_on(session, paper.id, f"Q{i:02d}?")
    await session.commit()

    first = result(await call("saved_answers", paper_id=str(paper.id)))
    rest = result(await call("saved_answers", paper_id=str(paper.id), offset=20))

    assert (first["total"], len(first["answers"]), first["answers"][0]["question"]) == (21, 20, "Q20?")
    assert [a["question"] for a in rest["answers"]] == ["Q00?"]


async def test_saved_answers_needs_a_paper_or_a_workspace_not_neither(session):
    answer = await call("saved_answers")

    assert answer.is_error and answer.structured_content["error"] == "invalid_scope"


async def test_saved_answers_takes_a_paper_or_a_workspace_not_both(session):
    answer = await call("saved_answers", paper_id=str(uuid.uuid4()), workspace="x")

    assert answer.is_error and answer.structured_content["error"] == "invalid_scope"


async def test_saved_answers_for_an_unknown_paper_is_a_recoverable_error(session):
    answer = await call("saved_answers", paper_id=str(uuid.uuid4()))

    assert answer.is_error and answer.structured_content == {"error": "unknown_paper"}


async def test_the_four_read_tools_are_read_only(session):
    from mcp import Client

    from mcp_server import server

    async with Client(server.mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in ("paper_references", "list_datasets", "get_dataset", "saved_answers"):
        assert tools[name].annotations.read_only_hint is True, name
        assert tools[name].output_schema, name
        assert tools[name].description.startswith("Use "), name
