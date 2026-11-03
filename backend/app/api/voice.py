from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SpeechDep
from app.providers.base import SpeechUnavailable

router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceStatus(BaseModel):
    ready: bool
    detail: str | None = None


@router.get("/status")
async def status(speech: SpeechDep) -> VoiceStatus:
    try:
        ready = await speech.health()
    except SpeechUnavailable as e:
        return VoiceStatus(ready=False, detail=str(e))
    return VoiceStatus(ready=ready, detail=None if ready else "The voice program is still loading its models.")
