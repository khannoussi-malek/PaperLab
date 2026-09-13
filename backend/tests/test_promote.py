import uuid

import pytest
from sqlalchemy import delete, select

from app.core import notes
from app.core.errors import InvalidInput, NotFound
from app.models import Chunk, LLMOutput, Note, Paper, Provenance

pytestmark = pytest.mark.anyio

ANSWER = "Self-attention  relates\nevery position [C1]. Layers stack [C2]."


async def make_answer(session) -> tuple[LLMOutput, list[Chunk]]:
    """An answer citing three chunks; the third is deleted afterwards, as a re-ingest would."""
    paper = Paper(title="Promote paper", file_path="/nonexistent.pdf", status="ready", page_count=3)
    session.add(paper)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100 + i, 300, 120 + i], [72, 130, 200, 140]],
            text=f"chunk {i} text", embed_model="test", strategy_ver=1,
        )
        for i in range(3)
    ]
    session.add_all(chunks)
    await session.flush()
    output = LLMOutput(
        paper_id=paper.id, kind="chat", question="how?", content=ANSWER, model="fake", prompt_version=1,
        source_chunks=[c.id for c in chunks],
    )
    session.add(output)
    await session.commit()
    await session.execute(delete(Chunk).where(Chunk.id == chunks[2].id))
    return output, chunks


async def test_promote_creates_an_llm_note_anchored_on_the_cited_chunks(session):
    output, chunks = await make_answer(session)

    body = "  relates every\nposition [C1]. Layers stack [C2]. "  # whitespace differs from the answer

    note = await notes.promote_llm_fragment(session, output.id, body, [chunks[1].id, chunks[0].id, chunks[1].id])

    assert (note.provenance, note.source_id) == (Provenance.LLM, output.id)
    assert note.body == "relates every\nposition [C1]. Layers stack [C2]."
    assert sorted(note.anchors, key=lambda a: a.page) == [
        notes.Anchor(c.paper_id, c.page, [tuple(r) for r in c.bbox], c.text) for c in chunks[:2]
    ]


async def test_editing_a_promoted_note_flips_it_to_llm_edited(session):
    output, chunks = await make_answer(session)
    note = await notes.promote_llm_fragment(session, output.id, "Layers stack [C2].", [chunks[1].id])

    edited = await notes.update_note(session, note.id, body="Layers stack, per my reading.")

    assert (edited.provenance, edited.source_id) == (Provenance.LLM_EDITED, output.id)


async def test_promote_rejects_what_the_answer_cannot_back(session):
    output, chunks = await make_answer(session)

    with pytest.raises(NotFound):
        await notes.promote_llm_fragment(session, uuid.uuid4(), "Layers stack", [chunks[0].id])
    with pytest.raises(InvalidInput, match="selected text"):
        await notes.promote_llm_fragment(session, output.id, " \n ", [chunks[0].id])
    with pytest.raises(InvalidInput, match="^body_not_in_output$"):
        await notes.promote_llm_fragment(session, output.id, "Layers stack, I think", [chunks[0].id])
    with pytest.raises(InvalidInput, match="not a source of this answer"):
        await notes.promote_llm_fragment(session, output.id, "Layers stack", [uuid.uuid4()])
    with pytest.raises(InvalidInput, match="no longer exists"):
        await notes.promote_llm_fragment(session, output.id, "Layers stack", [chunks[2].id])


async def test_promote_rejects_empty_chunk_ids(session):
    output, chunks = await make_answer(session)

    with pytest.raises(InvalidInput, match="at least one cited chunk"):
        await notes.promote_llm_fragment(session, output.id, "Layers stack", [])

    assert list(await session.scalars(select(Note).where(Note.source_id == output.id))) == []


async def test_promote_collapses_anchors_sharing_page_and_bbox(session):
    paper = Paper(title="Dup paper", file_path="/nonexistent-dup.pdf", status="ready", page_count=1)
    session.add(paper)
    await session.flush()
    bbox = [[72, 100, 300, 120]]
    dup_chunks = [
        Chunk(
            paper_id=paper.id, ordinal=i, page=1, bbox=bbox, text=f"dup {i} text",
            embed_model="test", strategy_ver=1,
        )
        for i in range(2)
    ]
    session.add_all(dup_chunks)
    await session.flush()
    output = LLMOutput(
        paper_id=paper.id, kind="chat", question="how?", content="Same spot twice.", model="fake", prompt_version=1,
        source_chunks=[c.id for c in dup_chunks],
    )
    session.add(output)
    await session.commit()

    note = await notes.promote_llm_fragment(
        session, output.id, "Same spot twice.", [dup_chunks[0].id, dup_chunks[1].id]
    )

    assert len(note.anchors) == 1
    assert note.anchors[0].quoted_text == "dup 0 text"


async def test_promote_over_http_then_edit_flips_the_badge(client, session):
    output, chunks = await make_answer(session)

    payload = {"output_id": str(output.id), "body": "Layers stack [C2].", "chunk_ids": [str(chunks[1].id)]}

    created = await client.post("/api/notes/promote", json=payload)

    assert created.status_code == 201
    note = created.json()
    assert (note["provenance"], note["source_id"], note["body"]) == ("llm", str(output.id), "Layers stack [C2].")
    assert [(a["page"], a["quoted_text"]) for a in note["anchors"]] == [(2, "chunk 1 text")]
    edited = await client.patch(f"/api/notes/{note['id']}", json={"body": "Layers stack, noted."})
    assert edited.json()["provenance"] == "llm_edited"


async def test_promote_http_errors(client, session):
    output, chunks = await make_answer(session)

    async def promote(body="Layers stack", chunk_ids=(chunks[0].id,), output_id=output.id):
        payload = {"output_id": str(output_id), "body": body, "chunk_ids": [str(c) for c in chunk_ids]}
        return await client.post("/api/notes/promote", json=payload)

    assert (await promote(output_id=uuid.uuid4())).status_code == 404
    assert (await promote(body="   ")).status_code == 422
    not_in_output = await promote(body="my own words")
    assert (not_in_output.status_code, not_in_output.json()) == (422, {"detail": "body_not_in_output"})
    assert (await promote(chunk_ids=[uuid.uuid4()])).status_code == 422
    assert (await promote(chunk_ids=[chunks[2].id])).status_code == 422
    assert (await promote(chunk_ids=[])).status_code == 422
