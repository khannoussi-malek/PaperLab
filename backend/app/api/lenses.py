"""Section roles and reading lenses (M16): what each part of a paper is, and the reader's fixes."""

import uuid
from dataclasses import asdict

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core import lenses, sections
from app.schemas.lenses import LensOut, SectionOut, SectionRoleIn, SectionsOut

router = APIRouter(prefix="/api/papers", tags=["lenses"])


async def _sections_out(session: AsyncSession, paper_id: uuid.UUID) -> SectionsOut:
    found, picked = await lenses.paper_lenses(session, paper_id)
    return SectionsOut(
        sections=[SectionOut(**asdict(section)) for section in found],
        lenses=[LensOut(id=lens.id, label=lens.label, **asdict(chosen)) for lens, chosen in picked],
    )


@router.get("/{paper_id}/sections")
async def get_sections(paper_id: uuid.UUID, session: SessionDep) -> SectionsOut:
    """Every section with its role and every lens with its chunks, in reading order. 404 for an unknown paper."""
    return await _sections_out(session, paper_id)


@router.put("/{paper_id}/section-roles")
async def set_section_role(paper_id: uuid.UUID, payload: SectionRoleIn, session: SessionDep) -> SectionsOut:
    """The reader's role for a heading (null: back to the automatic role), then what GET returns, recomputed.
    404 for an unknown paper; 422 for an unknown role, or unknown_section when no chunk has that heading."""
    await sections.set_role(session, paper_id, payload.section_title, payload.role)
    return await _sections_out(session, paper_id)
