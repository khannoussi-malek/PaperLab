from fastapi import APIRouter

from app.core import reporting_guidelines
from app.schemas.reporting_guidelines import GuidelineOut

router = APIRouter(tags=["reporting-guidelines"])


@router.get("/api/reporting-guidelines", response_model=list[GuidelineOut])
async def list_guidelines():
    return reporting_guidelines.all_guidelines()
