from pydantic import BaseModel

from app.schemas.manuscript_checks import CheckFindingOut


class DoiCheckOut(BaseModel):
    checked: int
    not_checked: int
    findings: list[CheckFindingOut]
    counts: dict[str, int]
