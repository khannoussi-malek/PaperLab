"""The citation reviewer's runs (M27 slice D): split the open .tex file into sentences, queue one check per (sentence,
cited paper) and one per uncited sentence, and report progress. app.workers.manuscript_review judges them one at a time.
The reviewer only judges: no response carries wording for the researcher's text (D118)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections, manuscript_papers, manuscripts, queue
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.manuscript_sentences import Sentence, in_range, normalize_newlines, split_sentences
from app.models import (
    ManuscriptClaimCheck,
    ManuscriptClaimDismissal,
    ManuscriptReviewRun,
    Paper,
)

MAX_PAIRS = 30  # (sentence, paper) pairs that call the model; more refuses the run
MAX_UNCITED = 30  # uncited sentences classified per run; the rest are counted, never refused (R1)
MAX_PLAIN = 2000
LIVE = timedelta(minutes=10)  # a run or row untouched this long lost its worker
JOB = "check_manuscript_citations"
logger = logging.getLogger(__name__)


def _row(s: Sentence, ord_: int, kind: str, key: str | None, paper_id: uuid.UUID | None) -> dict:
    row = {
        "sentence_hash": s.hash,
        "sentence": s.norm,
        "plain": s.plain,
        "ord": ord_,
        "kind": kind,
        "cite_key": key,
        "paper_id": paper_id,
        "status": "queued",
    }
    if kind == "cited" and paper_id is None:
        row |= {"status": "done", "verdict": "cannot_verify", "reason": "key_not_found"}
    elif len(s.plain) > MAX_PLAIN:
        row |= {"status": "failed", "reason": "claim_too_long"}
    return row


def to_utf16(text_: str, offsets: list[int]) -> list[int]:
    """Code-point offsets into `text_` as UTF-16 code-unit offsets (what JavaScript and CodeMirror index by)."""
    out, units, at = [], 0, 0
    for offset in sorted(set(offsets)):
        units += sum(2 if ord(c) > 0xFFFF else 1 for c in text_[at:offset])
        at = offset
        out.append((offset, units))
    table = dict(out)
    return [table[o] for o in offsets]


def from_utf16(text_: str, offset: int) -> int:
    """A UTF-16 offset as a code-point offset; one inside a surrogate pair rounds to the character containing it."""
    units = 0
    for i, c in enumerate(text_):
        units += 2 if ord(c) > 0xFFFF else 1
        if units > offset:
            return i
    return len(text_)


def plan(targets: list[Sentence], papers: dict[str, uuid.UUID], include_uncited: bool) -> tuple[list[dict], int]:
    """The rows to insert in document order (cited first, then uncited) and the uncited sentences left unchecked."""
    unique = list({s.hash: s for s in targets}.values())
    cited, uncited = [s for s in unique if s.keys], [s for s in unique if not s.keys]
    pairs = {(s.hash, papers.get(k) or k): (s, k) for s in cited for k in s.keys}  # one row per sentence and paper
    rows = [_row(s, 0, "cited", k, papers.get(k)) for s, k in pairs.values()]
    short = [s for s in uncited if len(s.plain) <= MAX_PLAIN]  # an over-long one needs no model call, so no slot
    long = [s for s in uncited if len(s.plain) > MAX_PLAIN]
    skipped = max(0, len(short) - MAX_UNCITED) if include_uncited else 0
    kept = sorted(short[:MAX_UNCITED] + long, key=lambda s: s.start)
    rows += [_row(s, 0, "uncited", None, None) for s in kept] if include_uncited else []
    return [r | {"ord": i} for i, r in enumerate(rows)], skipped


def _live(run: ManuscriptReviewRun | None) -> bool:
    return run is not None and run.status in ("queued", "running") and datetime.now(UTC) - run.updated_at < LIVE


def run_out(run: ManuscriptReviewRun) -> dict:
    dead = run.status in ("queued", "running") and not _live(run)
    return {
        "id": run.id,
        "file": run.file_path,
        "status": "interrupted" if dead else run.status,
        "total": run.total,
        "done": run.done,
        "reason": run.reason,
        "include_uncited": run.include_uncited,
        "uncited_skipped": run.uncited_skipped,
        "created_at": run.created_at,
    }


async def _latest(session: AsyncSession, mid: uuid.UUID) -> ManuscriptReviewRun | None:
    return await session.scalar(
        select(ManuscriptReviewRun)
        .where(ManuscriptReviewRun.manuscript_id == mid)
        .order_by(ManuscriptReviewRun.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )


async def start(
    session: AsyncSession,
    mid: uuid.UUID,
    *,
    file: str,
    base: datetime,
    selection: tuple[int, int] | None,
    include_uncited: bool = True,
) -> dict:
    # Starts on one manuscript take turns to the commit: the later one sees the earlier run and refuses.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:mid))"), {"mid": str(mid)})
    await manuscripts.get(session, mid)
    await llm_connections.resolve(session, None)  # Conflict("no_model") before any row
    source = await manuscripts.read(session, mid, file)
    if source.text is None or not file.endswith(".tex"):
        raise InvalidInput("not_tex", detail="The reviewer reads .tex files.")
    if source.updated_at > base:
        raise Conflict("file_changed", updated_at=source.updated_at)
    if _live(await _latest(session, mid)):
        raise Conflict("review_running")
    source_text = normalize_newlines(source.text)  # the editor's buffer is always \n
    sentences = await asyncio.to_thread(split_sentences, source_text)
    if selection is not None:  # UTF-16 offsets in, as the editor counts them; the splitter counts code points
        selection = (from_utf16(source_text, selection[0]), from_utf16(source_text, selection[1]))
    targets = sentences if selection is None else in_range(sentences, *selection)
    papers = {p["key"]: p["paper_id"] for p in await manuscript_papers.list_papers(session, mid)}
    rows, skipped = plan(targets, papers, include_uncited)
    pairs = sum(r["status"] == "queued" and r["kind"] == "cited" for r in rows)
    if pairs > MAX_PAIRS:
        raise InvalidInput("too_many_claims", detail=f"{pairs} checks", count=pairs)
    await _replace_rows(session, mid, file, {s.hash for s in sentences}, {r["sentence_hash"] for r in rows})
    waiting = sum(r["status"] == "queued" for r in rows)
    run = ManuscriptReviewRun(
        manuscript_id=mid,
        file_path=file,
        status="queued" if waiting else "done",
        total=len(rows),
        done=len(rows) - waiting,
        include_uncited=include_uncited,
        uncited_skipped=skipped,
        updated_at=func.clock_timestamp(),
    )
    session.add(run)
    await session.flush()
    session.add_all(ManuscriptClaimCheck(manuscript_id=mid, run_id=run.id, file_path=file, **r) for r in rows)
    await session.commit()  # the job reads these rows on its own connection
    await session.refresh(run)
    if waiting:
        await _enqueue(session, run)
    return run_out(run)


async def _replace_rows(session, mid, file, current: set[str], rechecked: set[str]) -> None:
    """Out go this file's rows for sentences that no longer exist or are being checked again, and every older run."""
    C = ManuscriptClaimCheck
    await session.execute(
        delete(C).where(
            C.manuscript_id == mid,
            C.file_path == file,
            or_(C.sentence_hash.not_in(current), C.sentence_hash.in_(rechecked)),
        )
    )
    await session.execute(delete(ManuscriptReviewRun).where(ManuscriptReviewRun.manuscript_id == mid))


async def _enqueue(session: AsyncSession, run: ManuscriptReviewRun) -> None:
    try:
        await queue.enqueue(JOB, str(run.id))
    except Exception:
        logger.exception("could not queue the review run %s", run.id)
        await session.execute(delete(ManuscriptClaimCheck).where(ManuscriptClaimCheck.run_id == run.id))
        run.status, run.reason = "failed", "queue_unavailable"
        await session.commit()


async def _run(session: AsyncSession, mid: uuid.UUID, run_id: uuid.UUID) -> ManuscriptReviewRun:
    await manuscripts.get(session, mid)
    run = await session.scalar(
        select(ManuscriptReviewRun)
        .where(ManuscriptReviewRun.id == run_id, ManuscriptReviewRun.manuscript_id == mid)
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise NotFound("unknown_run")
    return run


async def cancel(session: AsyncSession, mid: uuid.UUID, run_id: uuid.UUID) -> dict:
    run = await _run(session, mid, run_id)
    if run.status in ("queued", "running"):
        run.cancel_requested = True  # the job stops after the row it is on
        await session.commit()
    return run_out(run)


def _item_status(row: ManuscriptClaimCheck, working: bool, now: datetime) -> str:
    stale = now - row.updated_at >= LIVE
    if (row.status == "running" and stale) or (row.status == "queued" and stale and not working):
        return "interrupted"
    return row.status


async def state(session: AsyncSession, mid: uuid.UUID, file: str) -> dict:
    await manuscripts.get(session, mid)
    run = await _latest(session, mid)
    found = (
        await session.execute(
            select(ManuscriptClaimCheck, Paper.title)
            .outerjoin(Paper, Paper.id == ManuscriptClaimCheck.paper_id)
            .where(ManuscriptClaimCheck.manuscript_id == mid, ManuscriptClaimCheck.file_path == file)
            .order_by(ManuscriptClaimCheck.ord)
            .execution_options(populate_existing=True)
        )
    ).all()
    now = datetime.now(UTC)
    working = any(r.status == "running" and now - r.updated_at < LIVE for r, _ in found)
    dismissed = await session.scalars(
        select(ManuscriptClaimDismissal.sentence_hash).where(ManuscriptClaimDismissal.manuscript_id == mid)
    )
    return {
        "run": run_out(run) if run else None,
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "file": r.file_path,
                "sentence_hash": r.sentence_hash,
                "sentence": r.sentence,
                "ord": r.ord,
                "cite_key": r.cite_key,
                "paper_id": r.paper_id,
                "paper_title": title,
                "status": _item_status(r, working, now),
                "verdict": r.verdict,
                "reason": r.reason,
                "quote": r.quote,
                "page": r.page,
                "chunk_id": r.chunk_id,
                "output_id": r.output_id,
                "model": r.model,
                "ai": True,
            }
            for r, title in found
        ],
        "dismissed": list(dismissed),
    }


async def dismiss(session: AsyncSession, mid: uuid.UUID, sentence_hash: str) -> None:
    await manuscripts.get(session, mid)
    await session.execute(
        insert(ManuscriptClaimDismissal).values(manuscript_id=mid, sentence_hash=sentence_hash).on_conflict_do_nothing()
    )
    await session.commit()


async def restore(session: AsyncSession, mid: uuid.UUID, sentence_hash: str) -> None:
    await manuscripts.get(session, mid)
    await session.execute(
        delete(ManuscriptClaimDismissal).where(
            ManuscriptClaimDismissal.manuscript_id == mid, ManuscriptClaimDismissal.sentence_hash == sentence_hash
        )
    )
    await session.commit()


def locate(text_: str) -> list[dict]:
    if len(text_) > paths.MAX_TEXT:
        raise InvalidInput("text_too_long", limit=paths.MAX_TEXT)
    found = split_sentences(text_)
    spans = to_utf16(text_, [o for s in found for o in (s.start, s.end)])  # UTF-16 code units, as in JS strings
    return [
        {"start": spans[2 * i], "end": spans[2 * i + 1], "hash": s.hash, "keys": list(s.keys)}
        for i, s in enumerate(found)
    ]
