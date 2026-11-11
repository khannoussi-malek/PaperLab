"""The citation reviewer over every .tex file of a manuscript (S2P B6). One run, file_path "*", rows tagged with their
real file and numbered across files in document order; app.workers.manuscript_review judges them as for one file."""

import asyncio
import uuid

from sqlalchemy import delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections, manuscript_papers, manuscripts
from app.core.errors import Conflict, InvalidInput
from app.core.manuscript_missing_keys import load_texts
from app.core.manuscript_review import MAX_PAIRS, _enqueue, _latest, _live, plan, run_out
from app.core.manuscript_sections import _INPUT, _code, _tex
from app.core.manuscript_sentences import split_sentences
from app.models import ManuscriptClaimCheck, ManuscriptReviewRun

ALL = "*"  # the run's file_path: its rows carry the real files
CONFIRM_PAIRS = MAX_PAIRS  # above this a start needs confirm_large
MAX_ALL_PAIRS = 600  # above this a start is refused


def tex_order(texts: dict[str, str], main: str) -> list[str]:
    """Document order: main, then each \\input / \\include depth first, then any file nothing reaches, by path."""
    seen: list[str] = []

    def walk(path: str) -> None:
        if path in seen or path not in texts:
            return
        seen.append(path)
        for line in texts[path].split("\n"):
            for m in _INPUT.finditer(_code(line)):
                walk(_tex(m.group(2).removeprefix("./")))

    walk(main)
    return seen + sorted(p for p in texts if p not in seen)


def _pairs(rows: list[dict]) -> int:
    return sum(r["status"] == "queued" and r["kind"] == "cited" for r in rows)


async def _plan_all(session: AsyncSession, mid: uuid.UUID, include_uncited: bool) -> list[tuple[str, list[dict], int]]:
    manuscript = await manuscripts.get(session, mid)
    texts = {
        p: t for p, t in await load_texts(session, mid) if p.endswith(".tex")
    }  # NOT manuscripts.files(): metadata only
    if not texts:
        raise InvalidInput("no_tex", detail="The reviewer reads .tex files.")
    papers = {p["key"]: p["paper_id"] for p in await manuscript_papers.list_papers(session, mid)}
    out = []
    for path in tex_order(texts, manuscript.main_file):
        sentences = await asyncio.to_thread(split_sentences, texts[path])
        rows, skipped = plan(sentences, papers, include_uncited)
        out.append((path, rows, skipped))
    return out


async def estimate(session: AsyncSession, mid: uuid.UUID, *, include_uncited: bool) -> dict:
    planned = await _plan_all(session, mid, include_uncited)
    pairs = sum(_pairs(rows) for _, rows, _ in planned)
    return {
        "files": [
            {"path": p, "pairs": _pairs(rows), "uncited": sum(r["kind"] == "uncited" for r in rows)}
            for p, rows, _ in planned
        ],
        "pairs": pairs,
        "uncited": sum(sum(r["kind"] == "uncited" for r in rows) for _, rows, _ in planned),
        "uncited_skipped": sum(s for _, _, s in planned),
        "confirm_above": CONFIRM_PAIRS,
        "max_pairs": MAX_ALL_PAIRS,
        "needs_confirm": pairs > CONFIRM_PAIRS,
    }


async def start_all(
    session: AsyncSession,
    mid: uuid.UUID,
    *,
    include_uncited: bool = True,
    confirm_remote: bool = False,
    confirm_large: bool = False,
) -> dict:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:mid))"), {"mid": str(mid)})  # as start()
    await manuscripts.get(session, mid)
    await llm_connections.refuse_unconfirmed_remote(session, confirm_remote)  # before any row
    if _live(await _latest(session, mid)):
        raise Conflict("review_running")
    planned = await _plan_all(session, mid, include_uncited)
    pairs = sum(_pairs(rows) for _, rows, _ in planned)
    if pairs > MAX_ALL_PAIRS:
        raise InvalidInput("too_many_claims", detail=f"{pairs} checks", count=pairs)
    if pairs > CONFIRM_PAIRS and not confirm_large:
        raise InvalidInput("confirm_large", detail=f"{pairs} checks", count=pairs)
    flat = [r | {"file_path": path} for path, rows, _ in planned for r in rows]
    flat = [r | {"ord": i} for i, r in enumerate(flat)]  # one numbering across files: the job goes file by file
    await session.execute(delete(ManuscriptClaimCheck).where(ManuscriptClaimCheck.manuscript_id == mid))
    await session.execute(delete(ManuscriptReviewRun).where(ManuscriptReviewRun.manuscript_id == mid))
    waiting = sum(r["status"] == "queued" for r in flat)
    run = ManuscriptReviewRun(
        manuscript_id=mid,
        file_path=ALL,
        status="queued" if waiting else "done",
        confirm_remote=confirm_remote,
        total=len(flat),
        done=len(flat) - waiting,
        include_uncited=include_uncited,
        uncited_skipped=sum(s for _, _, s in planned),
        updated_at=func.clock_timestamp(),
    )
    session.add(run)
    await session.flush()
    session.add_all(ManuscriptClaimCheck(manuscript_id=mid, run_id=run.id, **r) for r in flat)
    await session.commit()  # the job reads these rows on its own connection
    await session.refresh(run)
    if waiting:
        await _enqueue(session, run)
    return run_out(run)
