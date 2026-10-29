import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import provenance
from app.core.chunking import STRATEGY_VERSION, ChunkDraft
from app.core.errors import Conflict, Gone, InvalidInput, NotFound
from app.core.source_types import DETAILS_SOURCES
from app.models import Chunk, Paper, PaperEvent, PaperMerge, PaperStatus
from app.models.workspace_search import WorkspaceSearchHit

PDF_MAGIC = b"%PDF-"
# A paper saved without a PDF keeps its abstract as one chunk on this page (R2): PDF pages count from 1, so every
# consumer that shows or trusts a page says "abstract" for it, or leaves it out.
ABSTRACT_PAGE = 0

# What create_metadata_paper sets itself; a prefill naming one is refused rather than overriding it.
OWNED_BY_CREATE = frozenset({"id", "file_path", "status", "details_source"})

READING_PASSES = range(4)
TRIAGES = ("keep", "later", "drop")


async def create_paper(
    session: AsyncSession, filename: str, data: bytes, pdf_dir: Path, *, prefill: dict[str, Any] | None = None
) -> Paper:
    """`prefill`: columns already known, e.g. a found paper's title and IDs. They win over the placeholder title."""
    if not data.startswith(PDF_MAGIC):
        raise InvalidInput(f"{filename!r} is not a PDF")

    paper_id = uuid.uuid4()
    path = pdf_dir / f"{paper_id}.pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    # Title is a placeholder until extraction (and later enrichment) finds a real one.
    paper = Paper(id=paper_id, file_path=str(path), **{"title": Path(filename).stem or "untitled", **(prefill or {})})
    session.add(paper)
    try:
        await session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    await session.refresh(paper)
    return paper


def abstract_chunk_text(title: str, abstract: str) -> str:
    """What the abstract chunk holds, and what gets embedded: "<title>. <abstract>", so a search finds the title too."""
    return f"{title if title.endswith(('.', '?', '!')) else title + '.'} {abstract}"


def abstract_drafts(title: str, abstract: str | None) -> list[ChunkDraft]:
    """The one abstract chunk of a paper without a PDF, or none when it has no abstract."""
    if not abstract:
        return []
    text = abstract_chunk_text(title, abstract)
    return [ChunkDraft(ordinal=0, page=ABSTRACT_PAGE, bbox=[], section_title="Abstract", text=text)]


async def create_metadata_paper(
    session: AsyncSession, prefill: dict[str, Any], details_source: str, *, looked_for_pdf: bool = False
) -> Paper:
    """A paper saved without a PDF (R5): `prefill` as create_paper takes it, and where the details came from, which
    also stamps every group it fills (R22). `looked_for_pdf`: the caller's free-copy lookup just found none, which
    counts as a check (now, "none"), so the weekly re-check waits a week before repeating it.

    With an abstract it gets one chunk on ABSTRACT_PAGE and starts `embedding`, for the caller to enqueue
    index_abstract; without one it is `ready` at once, with no chunks (R3). Commits; enqueues nothing.
    Raises InvalidInput("unknown_details_source", allowed=[...] | "reserved_field", fields=[...] | "empty_title").
    A blank abstract is stored as none.
    """
    if details_source not in DETAILS_SOURCES:
        raise InvalidInput("unknown_details_source", allowed=list(DETAILS_SOURCES))
    if reserved := sorted(OWNED_BY_CREATE.intersection(prefill)):
        raise InvalidInput("reserved_field", fields=reserved)
    title = (prefill.get("title") or "").strip()
    if not title:
        raise InvalidInput("empty_title")
    abstract = (prefill.get("abstract") or "").strip() or None
    values = {**prefill, "title": title, "abstract": abstract}
    paper = Paper(
        **{**values, "field_sources": provenance.sources_of(values, details_source)},
        file_path=None,
        details_source=details_source,
        status=PaperStatus.EMBEDDING if abstract else PaperStatus.READY,
        **(no_free_pdf_check() if looked_for_pdf else {}),
    )
    session.add(paper)
    await session.flush()
    await replace_chunks(session, paper.id, abstract_drafts(paper.title, abstract))  # commits paper and chunk together
    await session.refresh(paper)
    return paper


def no_free_pdf_check() -> dict[str, Any]:
    """The columns of a free-copy lookup that found nothing just now (R20)."""
    return {"pdf_checked_at": datetime.now(timezone.utc), "pdf_check_result": "none"}


async def record_no_free_pdf(session: AsyncSession, paper_id: uuid.UUID) -> None:
    """A lookup for a free copy of a held paper found none: it counts as a check. Commits."""
    await session.execute(update(Paper).where(Paper.id == paper_id).values(**no_free_pdf_check()))
    await session.commit()


async def attach_pdf(session: AsyncSession, paper_id: uuid.UUID, data: bytes, how: str) -> Paper:
    """The upgrade (R10): a paper saved without a PDF gets one, in place. Writes pdf_dir/<id>.pdf, sets file_path and
    `uploaded`, and moves its awaiting_pdf hits to `how` ("manual" for an upload, "imported" for a found copy) and
    records a pdf_attached event (R21) in the same commit, whichever path the PDF came by. Its id, tags, notes,
    workspaces, decisions, details_source and locked fields are untouched. The caller enqueues ingest_paper, which
    replaces the abstract chunk with the PDF's. The size cap is the caller's: an upload's is not a found copy's.
    Raises NotFound, InvalidInput("not_a_pdf"), Conflict("already_has_pdf")."""
    from app.core import retrieved_hits  # here: retrieved_hits -> tags -> enrichment imports this module

    if not data.startswith(PDF_MAGIC):
        raise InvalidInput("not_a_pdf")
    if how not in retrieved_hits.ARRIVALS:
        raise ValueError(f"how must be manual or imported, not {how!r}")
    # Locked until the commit: a second attach waits here, then finds the file instead of overwriting it.
    paper = await session.get(Paper, paper_id, with_for_update=True, populate_existing=True)
    if paper is None:
        raise NotFound(f"paper {paper_id} not found")
    if paper.has_pdf:  # the lock lasts until the caller's transaction ends
        raise Conflict("already_has_pdf")
    path = settings.pdf_dir / f"{paper.id}.pdf"
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ponytail: a cancel can't stop the writing thread, which may still leave a file here; the next attach
        # overwrites it. A commit whose ack is lost after the server committed unlinks a file the row names: rare.
        await asyncio.to_thread(path.write_bytes, data)
        paper.file_path, paper.status, paper.status_error = str(path), PaperStatus.UPLOADED, None
        await retrieved_hits.pdf_arrived(session, paper.id, how)
        session.add(PaperEvent(paper_id=paper.id, kind="pdf_attached", detail={"how": how}))
        await session.commit()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    await session.refresh(paper)
    return paper


async def get_paper(session: AsyncSession, paper_id: uuid.UUID, *, lock: bool = False) -> Paper:
    """Raises NotFound, or Gone for a merged paper. `lock`: the row is read afresh and locked until the commit."""
    paper = await session.get(Paper, paper_id, with_for_update=True if lock else None, populate_existing=lock)
    if paper is None:
        # the one indexed lookup, only here: a merged paper's id leads to the paper it became (R19)
        kept = await session.scalar(
            select(PaperMerge.kept_id)
            .where(PaperMerge.merged_id == paper_id, PaperMerge.status == "merged")
            .order_by(PaperMerge.created_at.desc())
            .limit(1)
        )
        if kept is not None:
            raise Gone("paper_merged", detail=f"This paper was merged into {kept}.", kept_id=str(kept))
        raise NotFound(f"paper {paper_id} not found")
    return paper


READING_SOURCES = ("reader", "library")


async def set_reading(
    session: AsyncSession, paper_id: uuid.UUID, changes: dict[str, Any], *, source: str = "reader"
) -> Paper:
    """The reader's own record of a paper: passes finished and their decision (D118, D119). Only the keys sent change.
    Never touches manual_fields. Raises NotFound, InvalidInput("reading_pass_out_of_range", allowed=[0, 3]),
    InvalidInput("unknown_triage", allowed=[...]), InvalidInput("nothing_to_set"),
    InvalidInput("unknown_source", allowed=["reader", "library"]). A real change also appends one triage event."""
    from app.core import triage  # triage imports this module

    if source not in READING_SOURCES:
        raise InvalidInput("unknown_source", allowed=list(READING_SOURCES))
    values = {key: changes[key] for key in ("reading_pass", "triage") if key in changes}
    if not values:
        raise InvalidInput("nothing_to_set")
    if "reading_pass" in values and values["reading_pass"] not in READING_PASSES:
        raise InvalidInput("reading_pass_out_of_range", allowed=[READING_PASSES[0], READING_PASSES[-1]])
    if values.get("triage") is not None and values["triage"] not in TRIAGES:
        raise InvalidInput("unknown_triage", allowed=list(TRIAGES))
    paper = await get_paper(session, paper_id, lock=True)  # lock order: the papers row first
    before = (paper.triage, paper.reading_pass)
    after = (values.get("triage", before[0]), values.get("reading_pass", before[1]))
    await session.execute(update(Paper).where(Paper.id == paper_id).values(**values))
    if after != before:
        triage.log_change(session, paper, source=source, before=before, after=after)
    await session.commit()
    await session.refresh(paper)
    return paper


async def list_papers(session: AsyncSession) -> list[Paper]:
    return list(await session.scalars(select(Paper).order_by(Paper.created_at.desc())))


async def list_chunks(session: AsyncSession, paper_id: uuid.UUID, page: int | None = None) -> list[Chunk]:
    await get_paper(session, paper_id)
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    if page is not None:
        query = query.where(Chunk.page == page)
    return list(await session.scalars(query))


async def set_status(
    session: AsyncSession, paper_id: uuid.UUID, status: PaperStatus, error: str | None = None, **fields
) -> None:
    """Commits immediately so the UI can watch the pipeline progress."""
    await session.execute(
        update(Paper).where(Paper.id == paper_id).values(status=status, status_error=error, **fields)
    )
    await session.commit()


async def replace_chunks(session: AsyncSession, paper_id: uuid.UUID, drafts: list[ChunkDraft]) -> None:
    """Delete-then-insert in one transaction, so re-running ingestion is idempotent."""
    await session.execute(delete(Chunk).where(Chunk.paper_id == paper_id))
    session.add_all(
        Chunk(
            paper_id=paper_id,
            ordinal=d.ordinal,
            page=d.page,
            bbox=d.bbox,
            section_title=d.section_title,
            text=d.text,
            embed_model=settings.embed_model,
            strategy_ver=STRATEGY_VERSION,
        )
        for d in drafts
    )
    await session.commit()


async def delete_paper(session: AsyncSession, paper_id: uuid.UUID) -> None:
    """Chunks and note anchors cascade. Notes survive: they are the primary object. Hits awaiting this paper's PDF
    go back to `failed`, for Get PDFs and link to take up again, instead of awaiting no paper. The row is locked
    first: a delete that waited on a merge of this paper finds it Gone, and never unlinks the file that is K's now."""
    paper = await get_paper(session, paper_id, lock=True)
    await session.execute(
        update(WorkspaceSearchHit)
        .where(WorkspaceSearchHit.paper_id == paper_id, WorkspaceSearchHit.acquisition_status == "awaiting_pdf")
        .values(acquisition_status="failed", paper_id=None)
    )
    await session.delete(paper)
    await session.commit()
    if paper.file_path:  # a paper saved without a PDF has no file to remove
        await asyncio.to_thread(Path(paper.file_path).unlink, missing_ok=True)


async def get_paper_file(session: AsyncSession, paper_id: uuid.UUID) -> Path:
    paper = await get_paper(session, paper_id)
    if paper.file_path is None:
        raise NotFound("no_pdf", detail="This paper has no PDF yet.")
    path = Path(paper.file_path)
    if not await asyncio.to_thread(path.is_file):
        raise NotFound(f"PDF for paper {paper_id} is missing from storage")
    return path


async def set_embeddings(
    session: AsyncSession, chunk_ids: list[uuid.UUID], vectors: list[list[float]], model_name: str
) -> None:
    """One executemany UPDATE by primary key, recording which source's model the vectors came from (D151): the
    embedder's name, so a switch never has to read settings.

    Not unnest(): pgvector's ARRAY(Vector) bind fails ("expected list or ndarray"), and 500 rows take under a second.
    """
    rows = [
        {"id": chunk_id, "embedding": vector, "embed_model": model_name}
        for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
    ]
    await session.execute(update(Chunk), rows)
    await session.commit()
