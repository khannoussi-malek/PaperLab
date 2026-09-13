"""Branches the M3 happy-path tests leave uncovered: empty quotes, repeated LLM edits, unknown ids."""

import uuid

import pytest

from app.core import notes
from app.core.errors import InvalidInput
from app.models import Note, Paper, Provenance

pytestmark = pytest.mark.anyio


async def test_whitespace_only_quote_is_rejected(session):
    paper = Paper(title="edge paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.commit()

    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", notes.Anchor(paper.id, 1, [(1.0, 2.0, 3.0, 4.0)], "  \n "))


async def test_llm_edited_note_stays_llm_edited_on_later_edits(session):
    note = Note(body="model said", provenance=Provenance.LLM)
    session.add(note)
    await session.commit()

    await notes.update_note_body(session, note.id, "edit one")
    assert (await notes.update_note_body(session, note.id, "edit two")).provenance == Provenance.LLM_EDITED


async def test_unknown_ids_are_404_on_every_notes_route(client):
    missing = uuid.uuid4()
    assert (await client.get(f"/api/papers/{missing}/notes")).status_code == 404
    assert (await client.patch(f"/api/notes/{missing}", json={"body": "x"})).status_code == 404
    assert (await client.delete(f"/api/notes/{missing}")).status_code == 404
    assert (await client.delete(f"/api/papers/{missing}")).status_code == 404


async def test_blank_quote_over_http_is_422(client, session):
    paper = Paper(title="edge paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.commit()
    anchor = {"paper_id": str(paper.id), "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "   "}

    assert (await client.post("/api/notes", json={"anchor": anchor})).status_code == 422
