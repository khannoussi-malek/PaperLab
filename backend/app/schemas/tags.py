import uuid

from pydantic import BaseModel


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    papers: int
    peer_reviewed: int
    preprint: int
    unknown_review: int
    full_text: int
    abstract: int
    metadata: int


class TagApply(BaseModel):
    tag: str  # checked (1..64 characters) by core/tags.py, which answers 422
    paper_ids: list[uuid.UUID]


class TagResultOut(BaseModel):
    tag: str
    changed: int
    unchanged: int
    skipped: list[str]


class TagRename(BaseModel):
    new_name: str


class TagRenamed(BaseModel):
    old: str
    new: str


class TagDeleted(BaseModel):
    tag: str
    papers: int


class PaperTagGroup(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    tags: list[str]
