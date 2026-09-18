"""The links the owner draws between two papers (P6, D110). The graph payload carries them, so there is no list
route: these three only write."""

import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import paper_links
from app.schemas.graph import LinkIn, LinkOut, LinkUpdate

router = APIRouter(tags=["links"])


@router.post("/api/links", status_code=201)
async def create_link(payload: LinkIn, session: SessionDep) -> LinkOut:
    """404 an unknown paper, 409 a pair already linked, 422 a bad label or the same paper twice."""
    return await paper_links.create(session, payload.from_paper, payload.to_paper, payload.label)


@router.patch("/api/links/{link_id}")
async def rename_link(link_id: uuid.UUID, payload: LinkUpdate, session: SessionDep) -> LinkOut:
    """Only the label changes. 404 gone, 422 a bad label."""
    return await paper_links.set_label(session, link_id, payload.label)


@router.delete("/api/links/{link_id}", status_code=204)
async def delete_link(link_id: uuid.UUID, session: SessionDep) -> None:
    """404 gone."""
    await paper_links.remove(session, link_id)
