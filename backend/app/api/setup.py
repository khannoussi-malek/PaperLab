"""The first-run setup's flag: GET says whether the app opens #/setup on start; PUT {"done": true} is Finish and Skip,
and {"done": false} exists for tests."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StrictBool

from app.api.deps import SessionDep
from app.core import setup

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupOut(BaseModel):
    done: bool


class SetupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Strict: "yes" or 1 is a 422, not a quiet true.
    done: StrictBool


@router.get("")
async def get_setup(session: SessionDep) -> SetupOut:
    return SetupOut(done=await setup.is_done(session))


@router.put("")
async def put_setup(payload: SetupIn, session: SessionDep) -> SetupOut:
    return SetupOut(done=await setup.set_done(session, payload.done))
