"""The section reviewer's runs (M27 slice E): find the section under the cursor, capture its text, sentences and the
researcher's own notes on the row, and queue one model call. The job reads only the row, so the result belongs to the
section's hash by construction. A response holds ids, labels, points and references to the researcher's own sentences
and notes, never text for their prose (D118)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections, manuscript_papers, manuscripts, queue
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.manuscript_review import from_utf16, to_utf16
from app.core.manuscript_section_text import Slice, section_slices
from app.core.manuscript_sentences import normalize_newlines, split_sentences
from app.core.section_rubrics import rubric_for
from app.models import ManuscriptSectionReview as Row
from app.models import Note, note_anchors, note_papers
from app.models.note import Provenance

LIVE = timedelta(minutes=20)  # one long local-model call has no heartbeat inside it
MAX_SOURCE = 60_000
MAX_SENTENCES = 150
MAX_NOTES = 12
NOTE_CHARS = 400
PREVIEW_WORDS = 8
JOB = "review_manuscript_section"
logger = logging.getLogger(__name__)


def _live(row: Row) -> bool:
    return row.status in ("queued", "running") and datetime.now(UTC) - row.updated_at < LIVE


def review_out(row: Row) -> dict:
    dead = row.status in ("queued", "running") and not _live(row)
    return {
        "id": row.id,
        "file": row.file_path,
        "section_hash": row.section_hash,
        "title": row.title,
        "role": row.role,
        "role_source": row.role_source,
        "status": "interrupted" if dead else row.status,
        "reason": row.reason,
        "findings": row.findings or [],
        "dropped": row.dropped,
        "model": row.model,
        "ai": True,
        "created_at": row.created_at,
    }


def _section_at(slices: list[Slice], pos: int) -> Slice:
    found = next((s for s in slices if s.start <= pos < s.end), None) or next(
        (s for s in slices[-1:] if pos == s.end), None
    )
    if found is None:
        raise InvalidInput("no_section", detail="Put the cursor inside a section.")
    return found


def _role(chosen: str | None, section: Slice) -> tuple[str, str]:
    role = chosen or section.guess
    if role is None:
        rubric_for("other")  # raises unknown_role: the researcher picks what kind of section this is
    rubric_for(role)  # validates a chosen role too
    return role, "chosen" if chosen else "guessed"


def _label(paper: dict, page: int | None) -> str:
    parts = [paper["first_author"] or "Unknown", str(paper["year"]) if paper["year"] else None]
    return " ".join(p for p in parts if p) + (f" p.{page}" if page else "")


async def _notes(session: AsyncSession, papers: list[dict], cited: set[str]) -> list[dict]:
    """The researcher's own notes (never the model's) on the citable papers: cited papers first, then newest."""
    by_paper = {p["paper_id"]: p for p in papers}
    if not by_paper:
        return []
    page = func.min(note_anchors.c.page)
    anchored = and_(note_anchors.c.note_id == Note.id, note_anchors.c.paper_id == note_papers.c.paper_id)
    query = (
        select(Note.id, Note.body, note_papers.c.paper_id, page)
        .join(note_papers, note_papers.c.note_id == Note.id)
        .outerjoin(note_anchors, anchored)
        .where(Note.provenance == Provenance.HUMAN.value, note_papers.c.paper_id.in_(list(by_paper)))
        .group_by(Note.id, note_papers.c.paper_id)
        .order_by(Note.created_at.desc(), Note.id)
    )
    seen: dict[uuid.UUID, dict] = {}
    for note_id, body, paper_id, first_page in await session.execute(query):
        paper = by_paper[paper_id]
        seen.setdefault(
            note_id,
            {
                "note_id": str(note_id),
                "paper_id": str(paper_id),
                "label": _label(paper, first_page),
                "body": body[:NOTE_CHARS],
                "cited": paper["key"] in cited,
            },
        )
    return sorted(seen.values(), key=lambda n: not n["cited"])[:MAX_NOTES]  # stable: newest first within each group


async def start(
    session: AsyncSession,
    mid: uuid.UUID,
    *,
    file: str,
    base: datetime,
    at: int,
    role: str | None,
    confirm_remote: bool,
) -> dict:
    # Starts on one manuscript take turns to the commit: the later one sees the earlier row and refuses.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:mid))"), {"mid": str(mid)})
    manuscript = await manuscripts.get(session, mid)
    source = await manuscripts.read(session, mid, file)
    if source.text is None or not file.endswith(".tex"):
        raise InvalidInput("not_tex", detail="The reviewer reads .tex files.")
    await llm_connections.refuse_unconfirmed_remote(session, confirm_remote)
    if source.updated_at > base:
        raise Conflict("file_changed", updated_at=source.updated_at)
    live = await session.scalars(
        select(Row)
        .where(Row.manuscript_id == mid, Row.status.in_(("queued", "running")))
        .execution_options(populate_existing=True)
    )
    if any(_live(r) for r in live):
        raise Conflict("review_running")
    full = normalize_newlines(source.text)  # the editor's buffer is always \n
    slices = section_slices(full, path=file, main_file=manuscript.main_file)
    section = _section_at(slices, from_utf16(full, at))
    chosen_role, role_source = _role(role, section)
    body = full[section.start : section.end]
    sentences = [s for s in split_sentences(body) if s.plain.strip()]
    if len(body) > MAX_SOURCE or len(sentences) > MAX_SENTENCES:
        raise InvalidInput("section_too_long", detail="Pick a shorter section.")
    papers = await manuscript_papers.list_papers(session, mid)
    notes = await _notes(session, papers, {k for s in sentences for k in s.keys})
    await session.execute(
        delete(Row).where(
            Row.manuscript_id == mid,
            Row.file_path == file,
            Row.section_hash.not_in([s.hash for s in slices]) | (Row.section_hash == section.hash),
        )
    )
    row = Row(
        manuscript_id=mid,
        file_path=file,
        section_hash=section.hash,
        title=section.title,
        role=chosen_role,
        role_source=role_source,
        status="queued",
        confirm_remote=confirm_remote,
        source=body,
        inputs={
            "sentences": [" ".join(s.plain.split()) for s in sentences],
            "hashes": [s.hash for s in sentences],
            "notes": [n["body"] for n in notes],
            "note_meta": [{k: n[k] for k in ("note_id", "paper_id", "label")} for n in notes],
        },
        updated_at=func.clock_timestamp(),
    )
    session.add(row)
    await session.commit()  # the job reads this row on its own connection
    await session.refresh(row)
    try:
        await queue.enqueue(JOB, str(row.id))
    except Exception:
        logger.exception("could not queue the section review %s", row.id)
        row.status, row.reason = "failed", "queue_unavailable"
        await session.commit()
    return review_out(row)


async def cancel(session: AsyncSession, mid: uuid.UUID, review_id: uuid.UUID) -> dict:
    await manuscripts.get(session, mid)
    row = await session.scalar(
        select(Row).where(Row.id == review_id, Row.manuscript_id == mid).execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFound("unknown_review")
    if row.status in ("queued", "running"):
        row.status, row.reason, row.updated_at = "failed", "cancelled", func.clock_timestamp()  # a late write misses
        await session.commit()
        await session.refresh(row)
    return review_out(row)


async def state(session: AsyncSession, mid: uuid.UUID, file: str) -> dict:
    await manuscripts.get(session, mid)
    found = await session.scalars(
        select(Row)
        .where(Row.manuscript_id == mid, Row.file_path == file)
        .order_by(Row.created_at)
        .execution_options(populate_existing=True)
    )
    return {"reviews": [review_out(r) for r in found]}


def locate(file: str, text_: str, main_file: str) -> list[dict]:
    if len(text_) > paths.MAX_TEXT:
        raise InvalidInput("text_too_long", limit=paths.MAX_TEXT)
    found = section_slices(text_, path=file, main_file=main_file)
    spans = to_utf16(text_, [o for s in found for o in (s.start, s.end)])  # UTF-16 code units, as in JS strings
    return [
        {
            "title": s.title,
            "start": spans[2 * i],
            "end": spans[2 * i + 1],
            "hash": s.hash,
            "words": s.words,
            "guess": s.guess,
        }
        for i, s in enumerate(found)
    ]
