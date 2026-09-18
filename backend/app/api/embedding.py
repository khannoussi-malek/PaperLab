"""The built-in search model and the index it builds: status, the model's download with live progress (D135), and
the confirmed library re-index."""

import asyncio
import logging
from collections.abc import AsyncIterable
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app.api.deps import SessionDep, TransportDep
from app.config import settings
from app.core import chat, embedding_index
from app.core.errors import Conflict
from app.db import SessionLocal
from app.providers import search_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/embedding", tags=["embedding"])

# One download at a time. ponytail: a lock per API process, and compose runs one; a second uvicorn worker would need
# a lock file in MODELS_DIR.
_downloading = asyncio.Lock()
ALREADY_RUNNING = "The search model is already downloading."
UNEXPECTED = "The download stopped because of an unexpected error. Try again: it resumes."
NOT_QUEUED = "The search model is ready, but your papers couldn't be queued for search. Re-index them in Settings."


class IndexedModelOut(BaseModel):
    model: str
    chunks: int


class EmbeddingStatusOut(BaseModel):
    model: str
    chunks: int
    indexed_with: list[IndexedModelOut]
    model_present: bool  # the built-in search model is downloaded
    download_bytes: int  # what Download would fetch now: the model's files, minus what a stopped download left
    unembedded_papers: int  # papers with chunks and no vectors; a finished download queues them (D137)
    papers_needing_search: int  # ready papers too long to send to chat whole (the library notice, P1)


class ReindexRequest(BaseModel):
    # Literal[True]: a missing or false flag is a 422, so nothing re-embeds without the explicit confirmation.
    confirm: Literal[True]


class ReindexOut(BaseModel):
    papers: int


# SSE payloads of the download: progress (repeated), then done, or error.
class DownloadProgressEvent(BaseModel):
    file: str
    completed: int  # bytes of the whole download, both files
    total: int


class DownloadDoneEvent(BaseModel):
    papers_queued: int


class DownloadErrorEvent(BaseModel):
    detail: str


# The route yields ServerSentEvent, so FastAPI can't see the payload models; listing them puts them in OpenAPI.
DOWNLOAD_RESPONSES = {200: {"model": DownloadProgressEvent | DownloadDoneEvent | DownloadErrorEvent}}


@router.get("")
async def embedding_status(session: SessionDep) -> EmbeddingStatusOut:
    return EmbeddingStatusOut(
        **asdict(await embedding_index.status(session, settings.embed_model)),
        model_present=search_model.present(settings.models_dir, search_model.SHIPPED),
        download_bytes=search_model.download_bytes(settings.models_dir, search_model.SHIPPED),
        unembedded_papers=len(await embedding_index.unembedded_papers(session)),
        papers_needing_search=await chat.papers_needing_search(session),
    )


async def download_allowed() -> None:
    """409s before the stream starts: the model is here already, or another download is running."""
    if search_model.present(settings.models_dir, search_model.SHIPPED):
        raise Conflict("model_present")
    if _downloading.locked():
        raise Conflict("download_running")


def download_error(detail: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data=DownloadErrorEvent(detail=detail))


@router.post(
    "/model",
    response_class=EventSourceResponse,
    responses=DOWNLOAD_RESPONSES,
    dependencies=[Depends(download_allowed)],
)
async def download_model(request: Request, transport: TransportDep) -> AsyncIterable[ServerSentEvent]:
    """Downloads the built-in search model into MODELS_DIR. Events: progress (repeated), then done with how many
    papers were queued for embedding (D137). error replaces done: a damaged file is deleted, anything else that
    arrived is kept for the next try. 409 model_present or download_running before the stream."""
    if _downloading.locked():  # another request started between the check and this stream
        yield download_error(ALREADY_RUNNING)
        return
    async with _downloading:
        try:
            async for progress in search_model.download(settings.models_dir, search_model.SHIPPED, transport):
                yield ServerSentEvent(event="progress", data=DownloadProgressEvent(**asdict(progress)))
        except search_model.DownloadError as exc:
            logger.warning("the search model download stopped: %s (%r)", exc, exc.__cause__)
            yield download_error(str(exc))
            return
        except Exception:
            logger.exception("the search model download failed unexpectedly")
            yield download_error(UNEXPECTED)
            return
    try:
        async with SessionLocal() as session:
            paper_ids = await embedding_index.unembedded_papers(session)
        for paper_id in paper_ids:
            await request.app.state.arq.enqueue_job("reembed_paper", str(paper_id))
    except Exception:
        # Without this the client waits for an event that never comes.
        logger.exception("queueing papers for embedding after the search model download failed")
        yield download_error(NOT_QUEUED)
        return
    yield ServerSentEvent(event="done", data=DownloadDoneEvent(papers_queued=len(paper_ids)))


@router.post("/reindex", status_code=202)
async def reindex_library(payload: ReindexRequest, request: Request, session: SessionDep) -> ReindexOut:
    """Queues one re-embed per paper with chunks. Chunk ids stay, so answers and notes keep their sources."""
    paper_ids = await embedding_index.indexed_papers(session)
    for paper_id in paper_ids:
        await request.app.state.arq.enqueue_job("reembed_paper", str(paper_id))
    return ReindexOut(papers=len(paper_ids))
