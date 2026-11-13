"""The reader's skills: list, create, edit, delete, reset and the per-kind default (M17 spec §6)."""

from typing import Literal

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import skills
from app.schemas.skills import SkillCreate, SkillDefaultIn, SkillOut, SkillUpdate

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_all(
    session: SessionDep,
    scope: Literal["paper", "workspace"] | None = None,
    include_hidden: bool = False,
) -> list[SkillOut]:
    return [
        SkillOut.model_validate(v, from_attributes=True)
        for v in await skills.list_skills(session, scope, include_hidden)
    ]


@router.post("", status_code=201)
async def create(payload: SkillCreate, session: SessionDep) -> SkillOut:
    view = await skills.create(session, **payload.model_dump())
    return SkillOut.model_validate(view, from_attributes=True)


@router.put("/{skill_id}")
async def update(skill_id: str, payload: SkillUpdate, session: SessionDep) -> SkillOut:
    view = await skills.update(session, skill_id, **payload.model_dump(exclude_unset=True))
    return SkillOut.model_validate(view, from_attributes=True)


@router.delete("/{skill_id}", status_code=204)
async def delete(skill_id: str, session: SessionDep) -> Response:
    await skills.delete(session, skill_id)
    return Response(status_code=204)


@router.post("/{skill_id}/reset")
async def reset(skill_id: str, session: SessionDep) -> SkillOut:
    return SkillOut.model_validate(await skills.reset(session, skill_id), from_attributes=True)


@router.post("/{skill_id}/default")
async def set_default(skill_id: str, payload: SkillDefaultIn, session: SessionDep) -> SkillOut:
    view = await skills.set_default(session, skill_id, payload.scope, payload.on)
    return SkillOut.model_validate(view, from_attributes=True)
