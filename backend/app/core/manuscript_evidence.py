"""Evidence for one sentence of a manuscript (M27 v2 stage 3): the library passages that bear on it, grouped by paper,
and one queued verdict per paper that app.workers.manuscript_evidence fills in."""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections, manuscript_papers, manuscripts, queue
from app.core.errors import Conflict, InvalidInput
from app.core.retrieval import retrieve
from app.models import ManuscriptEvidence

MAX_SENTENCE = 2000
PASSAGES = 8
STALE_AFTER = timedelta(minutes=5)  # a row `running` this long lost its worker
JOB = "verify_manuscript_evidence"


def sentence_hash(sentence: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", sentence.strip()).lower().encode()).hexdigest()


async def _has_model(session: AsyncSession) -> bool:
    try:
        await llm_connections.resolve(session, None)
    except Conflict:
        return False
    return True


async def find(session: AsyncSession, mid: uuid.UUID, sentence: str, *, embedder=None) -> dict:
    sentence = sentence.strip()
    if not sentence:
        raise InvalidInput("empty_claim", detail="The sentence is empty.")
    if len(sentence) > MAX_SENTENCE:
        raise InvalidInput("claim_too_long", detail=f"A sentence can be up to {MAX_SENTENCE} characters.")
    manuscript = await manuscripts.get(session, mid)
    if manuscript.workspace_id is None:
        raise InvalidInput("no_workspace", detail="Pick a workspace for this manuscript to find evidence.")
    keys = {p["paper_id"]: p["key"] for p in await manuscript_papers.list_papers(session, mid)}
    chunks = await retrieve(session, sentence, workspace_id=manuscript.workspace_id, k=PASSAGES, embedder=embedder)
    grouped: dict[uuid.UUID, list[dict]] = {}
    for c in chunks:
        if c.paper_id in keys:
            grouped.setdefault(c.paper_id, []).append({"chunk_id": c.id, "page": c.page, "text": c.text})
    h = sentence_hash(sentence)
    await _queue_rows(session, mid, h, sentence, list(grouped))
    queued = await _has_model(session) and bool(grouped)
    await session.commit()  # the job reads these rows on its own connection
    if queued:
        await queue.enqueue(JOB, str(mid), h)
    return {
        "sentence_hash": h,
        "papers": [{"paper_id": pid, "key": keys[pid], "passages": ps} for pid, ps in grouped.items()],
        "verdicts": "queued" if queued else "unavailable",
    }


async def _queue_rows(session, mid, h, sentence, paper_ids: list[uuid.UUID]) -> None:
    """One row per paper in rank order; a `done` row stays, every other one starts over."""
    where = (ManuscriptEvidence.manuscript_id == mid, ManuscriptEvidence.sentence_hash == h)
    await session.execute(delete(ManuscriptEvidence).where(*where, ManuscriptEvidence.paper_id.not_in(paper_ids)))
    if not paper_ids:
        return
    insert_ = insert(ManuscriptEvidence)
    table = ManuscriptEvidence.__table__

    def reset(column, value):  # a done row keeps what it has
        return case((table.c.status == "done", table.c[column]), else_=value)

    await session.execute(
        insert_.values([
            {"manuscript_id": mid, "sentence_hash": h, "sentence": sentence, "paper_id": pid, "rank": i,
             "status": "queued"}
            for i, pid in enumerate(paper_ids)
        ]).on_conflict_do_update(
            constraint="uq_manuscript_evidence_sentence_paper",
            set_={"rank": insert_.excluded.rank, "status": reset("status", "queued"),
                  "verdict": reset("verdict", None), "reason": reset("reason", None),
                  "quote": reset("quote", None), "page": reset("page", None),
                  "output_id": reset("output_id", None), "updated_at": reset("updated_at", func.now())},
        )
    )


async def rows(session: AsyncSession, mid: uuid.UUID, sentence_hash: str) -> list[dict]:
    await manuscripts.get(session, mid)
    found = await session.scalars(
        select(ManuscriptEvidence)
        .where(ManuscriptEvidence.manuscript_id == mid, ManuscriptEvidence.sentence_hash == sentence_hash)
        .order_by(ManuscriptEvidence.rank)
    )
    now = datetime.now(UTC)
    return [
        {
            "paper_id": r.paper_id,
            "rank": r.rank,
            "status": "interrupted" if r.status == "running" and now - r.updated_at >= STALE_AFTER else r.status,
            "verdict": r.verdict,
            "reason": r.reason,
            "quote": r.quote,
            "page": r.page,
            "output_id": r.output_id,
        }
        for r in found
    ]
