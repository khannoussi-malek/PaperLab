"""The papers a manuscript can cite (M27 v2 stage 2): the workspace's papers plus any it has pinned, with the keys
paperlab.bib uses, note counts, and a relevance ranking against a section's text."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.citations_export import _bibtex
from app.core.errors import NotFound
from app.core.manuscript_bib import key_state
from app.core.note_counts import note_counts
from app.core.retrieval import retrieve
from app.models import Manuscript, ManuscriptCiteKey, Paper


async def _citable(session, manuscript) -> tuple[list[Paper], dict[str, str], set[str]]:
    """Papers (workspace members, then pinned ones outside it) and {paper id: key} for the pinned ones."""
    items, rows, pins, generated = await key_state(session, manuscript)
    keys = {pid: key for key, pid in generated.items()}
    pinned = {pid: key for pid, key in pins.items() if not pid.startswith("orphan:")}
    wanted = [uuid.UUID(pid) for pid in dict.fromkeys([*items, *pinned])]
    found = {str(p.id): p for p in await session.scalars(select(Paper).where(Paper.id.in_(wanted)))} if wanted else {}
    papers = [found[pid] for pid in dict.fromkeys([*items, *pinned]) if pid in found]
    return papers, {**keys, **pinned}, set(pinned)


async def list_papers(session: AsyncSession, mid: uuid.UUID) -> list[dict]:
    manuscript = await manuscripts.get(session, mid)
    papers, keys, pinned = await _citable(session, manuscript)
    counts = await note_counts(session, [p.id for p in papers]) if papers else {}
    return [
        {
            "paper_id": p.id,
            "key": keys[str(p.id)],
            "pinned": str(p.id) in pinned,
            "title": p.title,
            "first_author": p.authors[0] if p.authors else None,
            "year": p.year,
            "has_pdf": p.has_pdf,
            "notes": counts[p.id]["notes"],
            "highlights": counts[p.id]["highlights"],
            "ai_notes": counts[p.id]["ai_notes"],
        }
        for p in papers
    ]


async def pin(session: AsyncSession, mid: uuid.UUID, paper_id: uuid.UUID) -> str:
    await manuscripts.get(session, mid)  # 404 first
    # Serialise pins on one manuscript (racing inserts would add the same row); read the pins after the lock.
    manuscript = await session.scalar(
        select(Manuscript).where(Manuscript.id == mid).with_for_update().execution_options(populate_existing=True)
    )
    items, _, pins, generated = await key_state(session, manuscript)
    pid = str(paper_id)
    if pid in pins:
        return pins[pid]
    if pid not in items:
        raise NotFound("unknown_paper")
    key = next(k for k, v in generated.items() if v == pid)
    bibtex = _bibtex([items[pid]], {pid: key}, publish=True)
    session.add(ManuscriptCiteKey(manuscript_id=mid, key=key, paper_id=paper_id, bibtex=bibtex))
    await session.flush()
    return key


async def rank(session: AsyncSession, mid: uuid.UUID, text: str, *, embedder=None) -> list[str]:
    manuscript = await manuscripts.get(session, mid)
    if not manuscript.workspace_id or not text.strip():
        return []
    chunks = await retrieve(session, text, workspace_id=manuscript.workspace_id, k=40, per_paper=1, embedder=embedder)
    return list(dict.fromkeys(str(c.paper_id) for c in chunks))
