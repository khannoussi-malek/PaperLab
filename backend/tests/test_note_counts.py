import uuid

import pytest
from sqlalchemy import insert

from app.core.note_counts import note_counts
from app.models import Note, Paper, Provenance, note_anchors, note_papers

pytestmark = pytest.mark.anyio


async def paper(session, title="P"):
    p = Paper(title=title)
    session.add(p)
    await session.flush()
    return p


async def note(session, provenance, *papers, anchored_on=()):
    n = Note(body="b", provenance=provenance)
    session.add(n)
    await session.flush()
    for p in papers:
        await session.execute(insert(note_papers).values(note_id=n.id, paper_id=p.id))
    for p in anchored_on:
        await session.execute(insert(note_anchors).values(
            note_id=n.id, paper_id=p.id, page=1, bbox=[1, 2, 3, 4], quoted_text="q"))


async def test_splits_per_paper_and_a_note_on_two_papers_counts_where_it_is_anchored(session):
    a, b, c = await paper(session, "A"), await paper(session, "B"), await paper(session, "C")
    await note(session, Provenance.HUMAN, a, b, anchored_on=[a])  # highlight on A, plain note on B
    await note(session, Provenance.HUMAN, a)
    await note(session, Provenance.LLM, b, anchored_on=[b])
    await note(session, Provenance.LLM_EDITED, b)
    missing = uuid.uuid4()
    got = await note_counts(session, [a.id, b.id, c.id, missing])
    assert got[a.id] == {"notes": 1, "highlights": 1, "ai_notes": 0}
    assert got[b.id] == {"notes": 1, "highlights": 0, "ai_notes": 2}
    assert got[c.id] == got[missing] == {"notes": 0, "highlights": 0, "ai_notes": 0}
    assert await note_counts(session, []) == {}


async def test_endpoint_returns_counts_and_caps_at_2000(client, session):
    a = await paper(session)
    await note(session, Provenance.HUMAN, a)
    await session.commit()
    ok = await client.post("/api/papers/note-counts", json={"paper_ids": [str(a.id)]})
    assert ok.status_code == 200
    assert ok.json() == {"counts": {str(a.id): {"notes": 1, "highlights": 0, "ai_notes": 0}}}
    big = await client.post("/api/papers/note-counts", json={"paper_ids": [str(uuid.uuid4()) for _ in range(2001)]})
    assert big.status_code == 422 and "too_many_papers" in big.text


async def test_endpoint_rejects_a_malformed_id_and_tolerates_duplicates_and_an_empty_list(client, session):
    a = await paper(session)
    await note(session, Provenance.HUMAN, a)
    await session.commit()
    bad = await client.post("/api/papers/note-counts", json={"paper_ids": ["not-a-uuid"]})
    assert bad.status_code == 422
    dup = await client.post("/api/papers/note-counts", json={"paper_ids": [str(a.id), str(a.id)]})
    assert dup.status_code == 200
    assert dup.json() == {"counts": {str(a.id): {"notes": 1, "highlights": 0, "ai_notes": 0}}}
    empty = await client.post("/api/papers/note-counts", json={"paper_ids": []})
    assert empty.status_code == 200 and empty.json() == {"counts": {}}
