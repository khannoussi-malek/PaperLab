"""The shape each JSON member of a workspace package must take (M35a review M2). Checked before anything is written:
a wrong type or a missing key is refused as package_invalid, never a server error. Extra keys are ignored, so a newer
PaperLab's additions still import."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.core.lenses import LensId
from app.models import NoteKind, Provenance

Text = StrictStr | None
Texts = list[StrictStr] | None
Rect = Annotated[list[StrictFloat], Field(min_length=4, max_length=4)]


class _Shape(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WorkspaceMeta(_Shape):
    name: StrictStr
    description: Text = None
    research_question: Text = None
    inclusion_criteria: Text = None
    exclusion_criteria: Text = None


class Manifest(_Shape):
    format: StrictStr
    format_version: StrictInt
    created_at: StrictStr
    workspace: WorkspaceMeta


class PaperRow(_Shape):
    key: StrictStr
    title: StrictStr
    doi: Text = None
    openalex_id: Text = None
    pmid: Text = None
    pmcid: Text = None
    abstract: Text = None
    authors: Texts = None
    year: StrictInt | None = None
    venue: Text = None
    type: Text = None
    source_type: Text = None
    peer_reviewed: Text = None
    published_doi: Text = None
    published_venue: Text = None
    volume: Text = None
    issue: Text = None
    pages: Text = None
    issn: Text = None
    editors: Texts = None
    manual_fields: Texts = None
    details_source: Text = None
    field_sources: dict[StrictStr, StrictStr] | None = None
    has_pdf: StrictBool | None = None
    pdf: Text = None


class Highlight(_Shape):
    paper: StrictStr
    page: StrictInt
    rects: list[Rect]
    quoted_text: Text = None


class NoteRow(_Shape):
    body: StrictStr
    provenance: Provenance
    kind: NoteKind | None = None
    color: Text = None
    created_at: Text = None
    updated_at: Text = None
    papers: Texts = None
    highlights: list[Highlight] | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def _is_a_timestamp(cls, value: str | None) -> str | None:
        if value:
            datetime.fromisoformat(value)  # ValueError becomes a ValidationError
        return value


class TagRow(_Shape):
    name: StrictStr
    papers: Texts = None


class PapersDoc(_Shape):
    papers: list[PaperRow]


class NotesDoc(_Shape):
    notes: list[NoteRow]


class TagsDoc(_Shape):
    tags: list[TagRow]


class SnapshotRow(_Shape):
    label: StrictStr
    paper: StrictStr
    page: StrictInt
    section: Text = None
    text: StrictStr
    from_abstract: StrictBool


MAX_SLOTS = 500  # far above any answer's sources; bounds what a crafted package makes the import allocate


def _is_slot(label: str, slots: int) -> bool:
    return label[:1] == "C" and label[1:].isdigit() and 1 <= int(label[1:]) <= slots


class AnswerRow(_Shape):
    question: Text = None
    content: StrictStr
    model: StrictStr
    connection_name: Text = None
    prompt_version: StrictInt
    skill_label: Text = None
    skill_version: StrictInt | None = None
    lens: LensId = "full"  # a package from before lens chat has none: the whole paper
    whole_paper: StrictBool
    notes_used: StrictInt | None = None
    notes_total: StrictInt | None = None
    created_at: StrictStr
    slots: Annotated[StrictInt, Field(ge=0, le=MAX_SLOTS)]
    cited: list[StrictStr]
    snapshot: list[SnapshotRow]

    @field_validator("created_at")
    @classmethod
    def _is_a_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value)  # ValueError becomes a ValidationError
        return value

    @model_validator(mode="after")
    def _labels_are_slots(self):
        labels = [*self.cited, *(entry.label for entry in self.snapshot)]
        if not all(_is_slot(label, self.slots) for label in labels):
            raise ValueError("a label names a citation slot the answer does not have")
        return self


class AnswersDoc(_Shape):
    answers: list[AnswerRow]


# ---- screening.json version 2 (M35c): the values the CHECK constraints allow, mirrored ----

RunStatus = Literal["running", "stopped", "exhausted", "failed"]
SourceMethod = Literal["database_search", "snowball_backward", "snowball_forward"]
Acquisition = Literal["not_attempted", "queued", "imported", "failed", "manual", "awaiting_pdf"]
Stage1 = Literal["relevant", "not_relevant", "maybe"]
ExcludeReason = Literal["wrong_topic", "wrong_study_type", "duplicate", "language", "inaccessible", "other"]
TopicFit = Literal["same_topic", "related_topic", "different_topic", "out_of_scope"]
Verdict = Literal["include", "exclude", "unsure"]
Stage2 = Literal["include", "exclude"]
LinkKind = Literal["search", "cites", "cited_by"]
BranchState = Literal["go_further", "stopped"]
SetBy = Literal["screening", "owner"]


SmallInt = Annotated[StrictInt, Field(ge=-(2**15), le=2**15 - 1)]  # a smallint column
Int4 = Annotated[StrictInt, Field(ge=-(2**31), le=2**31 - 1)]  # an integer column


def _aware(value: str | None) -> str | None:
    """A timestamp with its time zone, or None. A ValueError (through pydantic, a ValidationError) otherwise."""
    if value is not None and datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("a timestamp needs its time zone")
    return value


class CursorState(_Shape):
    """A source's paging state (the keys search_run_results and the pass logic read); anything else is dropped."""

    value: StrictInt | StrictStr | None = None  # Europe PMC pages by a string token, the rest by a number
    errors: StrictInt | None = None
    paused: StrictBool | None = None
    retry_after: Text = None
    disabled: StrictBool | None = None

    _timestamps = field_validator("retry_after")(_aware)


class CursorRow(_Shape):
    source: StrictStr
    exhausted: StrictBool
    cursor: CursorState = CursorState()
    last_error: Text = None


class StatsRow(_Shape):
    """A run's stats (the keys the search, the pass logic and PRISMA read); anything else is dropped on import."""

    warnings: list[dict] | None = None
    snowball: dict | None = None
    cut_short: StrictBool | None = None
    unfinished_sources: Texts = None
    paused_sources: Texts = None
    failed_sources: Texts = None
    per_source_raw_count: dict[StrictStr, StrictInt] | None = None
    per_source_out_of_range: dict[StrictStr, StrictInt] | None = None
    per_source_new_hits: dict[StrictStr, StrictInt] | None = None
    per_source_error: dict[StrictStr, StrictStr] | None = None
    pass_raw_count: dict[StrictStr, StrictInt] | None = None
    last_batch_new_hits: StrictInt | None = None
    passes: StrictInt | None = None
    prescreen_capped: dict | None = None


class RunRow(_Shape):
    key: StrictStr
    query: StrictStr
    sources: list[StrictStr]
    filters: dict
    query_overrides: dict | None = None
    status: RunStatus
    started_at: StrictStr
    stopped_at: Text = None
    stats: StatsRow
    cursors: list[CursorRow] = []

    _timestamps = field_validator("started_at", "stopped_at")(_aware)


class StageOne(_Shape):
    status: Stage1 | None = None
    exclude_reason: ExcludeReason | None = None
    note: Text = None


class StageTwo(_Shape):
    status: Stage2 | None = None
    exclude_reason: Text = None


class AiSuggestion(_Shape):
    ai: Literal[True]
    suggestion: Verdict
    reason: ExcludeReason | None = None
    note: Text = None
    model: Text = None
    relevance: Annotated[StrictInt, Field(ge=1, le=5)] | None = None
    confidence: Text = None
    quotes: list | None = None
    flags: list | None = None
    prompt_version: SmallInt | None = None
    suggested_at: Text = None

    _timestamps = field_validator("suggested_at")(_aware)


class HitRow(_Shape):
    key: StrictStr
    run: StrictStr
    title: StrictStr
    doi: Text = None
    external_ids: dict[StrictStr, StrictStr] | None = None
    authors: Texts = None
    year: Int4 | None = None
    venue: Text = None
    abstract: Text = None
    source_type: Text = None
    published_doi: Text = None
    published_venue: Text = None
    paper: Text = None
    source_method: SourceMethod
    seed_paper: Text = None
    snowball_round: Int4 | None = None
    first_seen_at: StrictStr
    acquisition_status: Acquisition
    priority: Annotated[StrictInt, Field(ge=1, le=5)] | None = None
    topic_fit: TopicFit | None = None
    stage1: StageOne
    stage1_decided_at: Text = None
    stage2: StageTwo | None = None
    ai_suggestion: AiSuggestion | None = None

    _timestamps = field_validator("first_seen_at", "stage1_decided_at")(_aware)


class EligibilityRow(_Shape):
    paper: StrictStr
    run: StrictStr
    stage2_status: Stage2 | None = None
    exclude_reason: Text = None
    assessed_at: Text = None

    _timestamps = field_validator("assessed_at")(_aware)


class LinkRow(_Shape):
    child_hit: StrictStr
    parent_hit: Text = None
    parent_paper: Text = None
    kind: LinkKind
    run: StrictStr


class BranchRow(_Shape):
    hit: Text = None
    paper: Text = None
    state: BranchState
    directions: Texts = None
    reason: Text = None
    set_by: SetBy


class ScreeningWorkspace(_Shape):
    screening_criteria: Text = None
    screening_ranked_used: StrictBool = False


class ScreeningV2(_Shape):
    version: Literal[2]
    runs: list[RunRow]
    hits: list[HitRow]
    eligibility: list[EligibilityRow] = []
    links: list[LinkRow] = []
    branches: list[BranchRow] = []
    workspace: ScreeningWorkspace = ScreeningWorkspace()


class CitationRow(_Shape):
    level: StrictInt
    identified: StrictInt
    relevant: StrictInt


class PrismaTotals(_Shape):
    """The numeric totals of prisma.json that the import's count check reads (the rest is for the reader)."""

    identified: StrictInt
    identified_databases: StrictInt
    duplicates_removed: StrictInt
    stage1_screened: StrictInt
    stage1_excluded: StrictInt
    stage1_excluded_by_reason: dict[StrictStr, StrictInt]
    sought: StrictInt
    not_retrieved: StrictInt
    stage2_assessed: StrictInt
    stage2_excluded: StrictInt
    stage2_excluded_by_reason: dict[StrictStr, StrictInt]
    included: StrictInt
    citation_searching: list[CitationRow]
