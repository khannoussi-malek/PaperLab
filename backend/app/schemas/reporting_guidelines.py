from pydantic import BaseModel


class ItemOut(BaseModel):
    id: str
    section: str
    text: str


class GuidelineOut(BaseModel):
    id: str
    label: str
    applies_to: str
    source: str
    items: list[ItemOut]
