from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import novelty
from app.schemas.novelty import NoveltyIn, NoveltyOut

router = APIRouter(prefix="/api/novelty", tags=["novelty"])


@router.post("")
async def check(body: NoveltyIn, session: SessionDep) -> NoveltyOut:
    """The library papers closest to a pasted idea, with their best passage and a plain label. Library only."""
    return NoveltyOut.model_validate(await novelty.check(session, body.text, body.workspace), from_attributes=True)
