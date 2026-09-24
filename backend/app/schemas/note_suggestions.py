import uuid

from pydantic import BaseModel

from app.schemas.papers import Rect


class NoteSuggestionOut(BaseModel):
    body: str
    chunk_id: uuid.UUID
    page: int
    section: str | None
    bbox: list[Rect]


class NoteSuggestionsOut(BaseModel):
    output_id: uuid.UUID  # promote one of these through POST /api/notes/promote, unchanged
    suggestions: list[NoteSuggestionOut]
