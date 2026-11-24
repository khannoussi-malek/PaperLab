"""Shapes for growing and tracing a search: snowballing, eligibility, PRISMA, branches and where each hit came from."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SnowballRequest(BaseModel):
    # An empty seed_paper_ids AND empty seed_hit_ids has no seed to hop from, so it would produce a run with zero
    # results and nothing recorded — reject it instead (same "reject rather than silently do nothing" convention
    # as SearchRunCreate.sources). Neither list alone is required (min_length=1 on just one would make the other
    # mandatory) — the model_validator below checks the combination.
    seed_paper_ids: list[uuid.UUID] = Field(default_factory=list)
    seed_hit_ids: list[uuid.UUID] = Field(default_factory=list)
    backward: bool = True
    forward: bool = True

    @model_validator(mode="after")
    def at_least_one_seed(self):
        if not self.seed_paper_ids and not self.seed_hit_ids:
            raise ValueError("at least one seed_paper_id or seed_hit_id is required")
        return self


class SnowballOut(BaseModel):
    new_hits: int
    skipped_seeds: list[uuid.UUID]
    errors: dict[str, str]


class SnowballNextOut(SnowballOut):
    remaining: int  # go-further items still listed after this batch


class EligibilityUpdate(BaseModel):
    status: Literal["include", "exclude"]
    # Free-text, unlike stage1's CHECK'd ExcludeReason enum — SearchRunEligibility.stage2_exclude_reason is a
    # plain TEXT column with no DB-level CHECK constraint (Task 1).
    exclude_reason: str | None = None


class EligibilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paper_id: uuid.UUID
    search_run_id: uuid.UUID
    stage2_status: str | None
    stage2_exclude_reason: str | None
    assessed_at: datetime | None


class CitationSearchingLevel(BaseModel):
    level: int
    identified: int
    relevant: int


class PrismaExportOut(BaseModel):
    sources_searched: list[str] = []
    sources_not_searched: list[str] = []  # failed or off, and returned nothing
    identified: int
    duplicates_removed: int
    stage1_screened: int
    stage1_excluded: int
    stage1_excluded_by_reason: dict[str, int]
    sought: int
    not_retrieved: int
    stage2_assessed: int
    stage2_excluded: int
    stage2_excluded_by_reason: dict[str, int]
    included: int
    runs: list[dict]
    automation: list[str] = []
    notes: list[str] = []
    screening_criteria: str | None = None
    citation_searching: list[CitationSearchingLevel] = []
    identified_databases: int = 0  # `identified` minus the snowball hits counted under citation_searching


class BranchIn(BaseModel):
    hit_id: uuid.UUID | None = None
    paper_id: uuid.UUID | None = None
    # required, null clears the decision; checked in core.branches so every caller gets the same InvalidInput
    state: str | None
    directions: list[str] = []
    reason: str | None = None


class BranchOut(BaseModel):
    hit_id: uuid.UUID | None
    paper_id: uuid.UUID | None
    state: str | None
    directions: list[str]
    reason: str | None


class NextItem(BaseModel):
    """One go_further branch with directions not yet snowballed. Exactly one of hit_id and paper_id is set."""

    hit_id: uuid.UUID | None = None
    paper_id: uuid.UUID | None = None
    title: str
    directions_left: list[str]


class ProvBranch(BaseModel):
    state: str
    directions: list[str]
    reason: str | None


class ProvNode(BaseModel):
    id: str  # hit id, "paper:<id>" for a hand-added paper, or "run:<id>:unknown"
    title: str
    year: int | None = None
    level: int
    decision: str | None = None
    suggestion: str | None = None
    relevance: int | None = None
    reason: str | None = None  # the AI's one-line reason, cut to 160 characters
    paper_id: uuid.UUID | None = None
    branch: ProvBranch | None = None
    snowballed: list[str] = []  # directions already run from this node
    paths: int = 0  # incoming links
    zero_found_error: str | None = None


class ProvLink(BaseModel):
    parent: str  # a node id, or "root:<run_id>" / "root:hand"
    child: str
    kind: str
    run_id: uuid.UUID | None = None
    created_at: datetime | None = None


class ProvRoot(BaseModel):
    id: str
    label: str
    hit_count: int
    on_tree: int
    excluded_hidden: int = 0  # excluded hits of this search left off the tree by the cap


class LevelStats(BaseModel):
    level: int
    found: int
    already_known: int
    included: int
    go_further: int
    stopped: int
    done: bool
    saturated: bool


class ProvenanceOut(BaseModel):
    nodes: list[ProvNode]
    links: list[ProvLink]
    roots: list[ProvRoot]
    levels: list[LevelStats]
    truncated: bool = False


class SuggestHitRequest(BaseModel):
    confirm_remote: bool = False  # the owner agreed to send the abstract to a remote default model
