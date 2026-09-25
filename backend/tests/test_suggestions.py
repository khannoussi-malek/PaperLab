"""Chat's suggested notes (D94, D96): `:::note` blocks read from the stored answer, and saved with a click."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.core import notes
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Chunk, LLMOutput, Note, Paper, Provenance, Workspace

pytestmark = pytest.mark.anyio

# The frontend's splitNoteBlocks is tested on these same cases (src/features/chat/noteBlocks.test.ts).
CASES = json.loads((Path(__file__).parents[2] / "frontend/src/features/chat/noteBlocks.cases.json").read_text())
ANSWER = (
    "Two ideas, from the method [C2].\n"
    ":::note\nSelf-attention relates every position [C1].\n:::\n"
    ":::note\nOne idea per note, as I noted [N1].\n:::\n"
    ":::note\n\n:::\n"
    ":::note\nBoth papers agree [C1][C3].\n:::"
)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_note_blocks(case):
    assert notes.note_blocks(case["content"]) == case["blocks"]


async def answer_on(
    session, *, paper_chat=True, kind="chat"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """ANSWER, saved with sources C1 = paper A's chunk 0, C2 = A's chunk 1, C3 = paper B's chunk 0. Returns plain ids
    (the answer, A, B, the chunks): a refused save rolls back, which expires every ORM object in the session."""
    a = Paper(title="A", file_path="/a.pdf", status="ready", page_count=2)
    b = Paper(title="B", file_path="/b.pdf", status="ready", page_count=2)
    session.add_all([a, b])
    await session.flush()
    chunks = [
        Chunk(paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100 + i, 300, 120 + i]],
              text=f"{paper.title} chunk {i}", embed_model="test", strategy_ver=1)
        for paper, i in ((a, 0), (a, 1), (b, 0))
    ]  # fmt: skip
    session.add_all(chunks)
    await session.flush()
    if paper_chat:
        scope = {"paper_id": a.id}
    else:
        workspace = Workspace(name=f"Suggestions {uuid.uuid4().hex[:8]}")
        session.add(workspace)
        await session.flush()
        scope = {"workspace_id": workspace.id}
    output = LLMOutput(kind=kind, question="Create notes", content=ANSWER, model="m", prompt_version=3,
                       source_chunks=[c.id for c in chunks], **scope)  # fmt: skip
    session.add(output)
    await session.commit()
    return output.id, a.id, b.id, [c.id for c in chunks]


async def test_the_body_is_the_block_verbatim_anchored_on_its_own_citations_only(session):
    output_id, a, _, _ = await answer_on(session)

    note = await notes.save_suggestion(session, output_id, 0)

    assert (note.body, note.provenance, note.source_id, note.color) == (
        "Self-attention relates every position [C1].",
        Provenance.LLM,
        output_id,
        notes.DEFAULT_COLOR,
    )
    # C1 only: the answer cites C2 too, but outside this block.
    assert [(x.paper_id, x.page, x.quoted_text) for x in note.anchors] == [(a, 1, "A chunk 0")]
    assert note.paper_ids == [a]
    assert await session.scalar(select(Note.source_block).where(Note.id == note.id)) == 0


async def test_in_paper_chat_a_block_citing_no_passage_still_links_the_paper(session):
    output_id, a, _, _ = await answer_on(session)

    note = await notes.save_suggestion(session, output_id, 1)

    assert (note.body, note.anchors, note.paper_ids) == ("One idea per note, as I noted [N1].", [], [a])


async def test_in_workspace_chat_a_block_links_every_paper_it_cites_or_none(session):
    output_id, a, b, _ = await answer_on(session, paper_chat=False)

    both = await notes.save_suggestion(session, output_id, 3)
    loose = await notes.save_suggestion(session, output_id, 1)

    assert (both.paper_ids, {x.paper_id for x in both.anchors}) == ([a, b], {a, b})
    assert (loose.paper_ids, loose.anchors) == ([], [])


async def test_saving_a_block_twice_is_refused_and_keeps_the_first(session):
    output_id, _, _, _ = await answer_on(session)
    first_id = (await notes.save_suggestion(session, output_id, 0)).id

    with pytest.raises(Conflict, match="^already_saved$"):
        await notes.save_suggestion(session, output_id, 0)

    saved = await session.execute(select(Note.id, Note.source_block).where(Note.source_id == output_id))
    assert saved.all() == [(first_id, 0)]


async def test_a_missing_block_an_empty_block_or_an_answer_that_is_not_a_chat_answer_is_refused(session):
    output_id, _, _, _ = await answer_on(session)
    mcp_id, _, _, _ = await answer_on(session, kind="mcp")

    with pytest.raises(InvalidInput, match="^no_such_block$"):
        await notes.save_suggestion(session, output_id, 4)
    with pytest.raises(InvalidInput, match="^empty_body$"):
        await notes.save_suggestion(session, output_id, 2)
    with pytest.raises(NotFound, match="^answer_not_found$"):
        await notes.save_suggestion(session, uuid.uuid4(), 0)
    with pytest.raises(NotFound, match="^answer_not_found$"):
        await notes.save_suggestion(session, mcp_id, 0)


async def test_a_block_citing_a_passage_a_re_ingest_replaced_is_refused_as_promote_refuses_it(session):
    output_id, _, _, chunk_ids = await answer_on(session)
    await session.execute(delete(Chunk).where(Chunk.id == chunk_ids[0]))

    with pytest.raises(InvalidInput, match="^a cited chunk no longer exists; the paper was re-ingested, so ask again$"):
        await notes.save_suggestion(session, output_id, 0)
