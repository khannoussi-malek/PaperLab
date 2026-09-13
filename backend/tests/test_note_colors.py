import pytest

from app.core import notes
from app.core.errors import InvalidInput
from app.models import Note, Paper, Provenance

pytestmark = pytest.mark.anyio


async def make_paper(session) -> Paper:
    paper = Paper(title="colour paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.commit()
    return paper


def anchor(paper: Paper) -> notes.Anchor:
    return notes.Anchor(paper_id=paper.id, page=1, bbox=[(72.0, 400.0, 290.0, 410.0)], quoted_text="a quote")


async def test_new_notes_default_to_yellow(session):
    note = await notes.create_human_note(session, "", anchor(await make_paper(session)))
    assert note.color == notes.DEFAULT_COLOR == "#facc15"


async def test_colour_is_stored_lowercased_on_create_and_update(session):
    note = await notes.create_human_note(session, "", anchor(await make_paper(session)), color="#4ADE80")
    assert note.color == "#4ade80"
    assert (await notes.update_note(session, note.id, color="#F472B6")).color == "#f472b6"


async def test_malformed_colours_are_rejected(session):
    paper = await make_paper(session)
    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", anchor(paper), color="red")
    note = await notes.create_human_note(session, "", anchor(paper))
    with pytest.raises(InvalidInput):
        await notes.update_note(session, note.id, color="#12345")


async def test_recolouring_keeps_llm_provenance_but_editing_the_body_flips_it(session):
    llm_note = Note(body="model said", provenance=Provenance.LLM)
    session.add(llm_note)
    await session.commit()

    recoloured = await notes.update_note(session, llm_note.id, color="#60a5fa")
    assert (recoloured.provenance, recoloured.color) == (Provenance.LLM, "#60a5fa")
    assert (await notes.update_note(session, llm_note.id, body="mine now")).provenance == Provenance.LLM_EDITED


async def test_colour_over_http(client, session):
    paper = await make_paper(session)
    anchor_json = {"paper_id": str(paper.id), "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}

    created = await client.post("/api/notes", json={"anchor": anchor_json, "color": "#4ADE80"})
    assert (created.status_code, created.json()["color"]) == (201, "#4ade80")
    note_id = created.json()["id"]

    recoloured = await client.patch(f"/api/notes/{note_id}", json={"color": "#60a5fa"})
    assert (recoloured.status_code, recoloured.json()["color"], recoloured.json()["body"]) == (200, "#60a5fa", "")

    assert (await client.post("/api/notes", json={"anchor": anchor_json, "color": "yellow"})).status_code == 422
    assert (await client.patch(f"/api/notes/{note_id}", json={"color": "#fff"})).status_code == 422
    assert (await client.patch(f"/api/notes/{note_id}", json={})).status_code == 422
