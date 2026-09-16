from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.config import settings
from app.core import embedding_index

router = APIRouter(prefix="/api/embedding", tags=["embedding"])


class IndexedModelOut(BaseModel):
    model: str
    chunks: int


class EmbeddingStatusOut(BaseModel):
    model: str
    chunks: int
    indexed_with: list[IndexedModelOut]


class ReindexRequest(BaseModel):
    # Literal[True]: a missing or false flag is a 422, so nothing re-embeds without the explicit confirmation.
    confirm: Literal[True]


class ReindexOut(BaseModel):
    papers: int


@router.get("")
async def embedding_status(session: SessionDep) -> EmbeddingStatusOut:
    return await embedding_index.status(session, settings.embed_model)


@router.post("/reindex", status_code=202)
async def reindex_library(payload: ReindexRequest, request: Request, session: SessionDep) -> ReindexOut:
    """Queues one re-embed per paper with chunks. Chunk ids stay, so answers and notes keep their sources."""
    paper_ids = await embedding_index.indexed_papers(session)
    for paper_id in paper_ids:
        await request.app.state.arq.enqueue_job("reembed_paper", str(paper_id))
    return ReindexOut(papers=len(paper_ids))
