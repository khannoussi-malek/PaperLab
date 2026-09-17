import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

LinkKind = Literal["cites", "same_workspace", "co_anchored", "co_authored", "shares_topic", "similar", "manual"]


class GraphNode(BaseModel):
    """A library paper. `workspaces` are names, oldest membership first: the first one colours the node."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    year: int | None
    workspaces: list[str]
    has_notes: bool
    status: str


class GraphLink(BaseModel):
    """One link per pair per kind. `id` and `label` are set only for a `manual` link (the owner's own)."""

    model_config = ConfigDict(from_attributes=True)

    source: uuid.UUID
    target: uuid.UUID
    kind: LinkKind
    id: uuid.UUID | None = None
    label: str | None = None


class GraphOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodes: list[GraphNode]
    links: list[GraphLink]
    truncated: bool


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_paper: uuid.UUID
    to_paper: uuid.UUID
    label: str


class LinkIn(BaseModel):
    from_paper: uuid.UUID
    to_paper: uuid.UUID
    label: str


class LinkUpdate(BaseModel):
    label: str
