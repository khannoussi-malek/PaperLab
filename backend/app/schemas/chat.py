import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.core.lenses import LensId
from app.schemas.papers import Rect

if TYPE_CHECKING:  # core must not import api, and schemas needn't import core at runtime
    from app.core import answer_provenance, chat
    from app.core.retrieval import RetrievedChunk


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    model_id: uuid.UUID | None = None  # a model from GET /api/llm/models; None asks the default
    parent_id: uuid.UUID | None = None  # the answer this question follows up; paper chat only
    skill_id: str | None = None  # the skill picked for this question; None runs the base prompt alone (M17)


class ChatSource(BaseModel):
    label: str  # "C1": the marker the answer cites
    chunk_id: uuid.UUID | None  # null when replaced: the passage's chunk is gone (M33)
    paper_id: uuid.UUID  # workspace chat cites several papers
    page: int
    section: str | None
    bbox: list[Rect] | None  # null when replaced: the page opens with no box
    from_abstract: bool  # a paper saved without a PDF: cite it as "abstract only", never by page
    replaced: bool  # a re-ingest replaced the chunk; the snapshot still says where the passage was (M33)


class NoteSource(BaseModel):
    label: str  # "N1": the marker the answer cites
    note_id: uuid.UUID
    paper_id: uuid.UUID  # the paper the prompt named it by
    page: int | None  # null: the note is on the whole paper
    provenance: Literal["human", "llm", "llm_edited"]


# SSE payloads, one model per event name: sources, token, done, error.
class SourcesEvent(BaseModel):
    whole_paper: bool  # the paper was small enough to send whole, so retrieval was skipped
    sources: list[ChatSource]
    notes: list[NoteSource]
    notes_used: int | None  # notes that fit the prompt
    notes_total: int | None  # every note in the paper or workspace


class HitMetaEvent(BaseModel):
    """First event of a search hit's chat: what the answer will read."""

    source: Literal["abstract", "full_text"]


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    output_id: uuid.UUID
    model: str
    connection_name: str
    prompt_version: int
    cited: list[str]  # C labels first-cited first, then N labels first-cited first
    skill_label: str | None  # the skill that ran, as it was named then; None with no skill
    lens: LensId  # the lens the sources came from; 'full' when the skill has none, or the paper had no sections for it


class ErrorEvent(BaseModel):
    message: str
    retryable: bool


class SavedNoteOut(BaseModel):
    index: int  # the answer's :::note block it was saved from, from 0
    note_id: uuid.UUID
    paper_ids: list[uuid.UUID]  # the note's papers now, by title: where the card's Open goes


class ChatAnswer(BaseModel):
    id: uuid.UUID
    question: str
    content: str
    model: str
    connection_name: str | None  # null for answers written before model connections existed
    prompt_version: int
    created_at: datetime
    whole_paper: bool
    # sources[i] is C{i+1}. null: a re-ingest replaced that chunk, so its marker renders as plain text.
    sources: list[ChatSource | None]
    # notes[i] is N{i+1}. null: the note was deleted, or is no longer linked to a paper in scope.
    notes: list[NoteSource | None]
    notes_used: int | None
    notes_total: int | None
    parent_id: uuid.UUID | None  # the answer this one follows up; null for a question asked on its own
    saved_notes: list[SavedNoteOut]  # its suggested notes already saved, by block
    skill_label: str | None  # the skill that ran, copied when the answer was written; null with no skill
    lens: LensId = "full"  # the lens the answer's sources came from (M16): 'full' unless a skill's lens applied
    chart_spec: dict | None = None  # a chart answer's spec (M14): dataset/column ids, drawn like a saved chart


class PromoteRequest(BaseModel):
    output_id: uuid.UUID
    body: str = Field(max_length=50_000)
    chunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SaveSuggestion(BaseModel):
    index: int = Field(ge=0)  # the answer's :::note block, from 0


class AnswerPassageOut(BaseModel):
    label: str  # "C1": the marker the answer cites
    paper_id: uuid.UUID | None  # null when not recorded and the chunk is gone
    paper_title: str | None
    page: int | None
    section: str | None
    text: str | None  # null when not recorded
    # current: still in the paper. changed: the text is no longer in it. not_recorded: nothing was kept to check.
    state: Literal["current", "changed", "not_recorded", "not_kept", "paper_removed"]


class AnswerProvenanceOut(BaseModel):
    """How an answer was made (M33). Computed on request, never on the history lists."""

    model: str
    connection_name: str | None
    prompt_version: int
    skill_label: str | None
    lens: LensId  # the lens the answer read through; 'full' is the whole paper
    created_at: datetime
    out_of_date: bool  # a cited passage changed since the answer was written
    passages: list[AnswerPassageOut]


class McpNoteOut(BaseModel):
    """A note an MCP client added: the view says where it came from and nothing more."""

    source: Literal["claude_desktop"]


def to_sources(
    chunks: "list[RetrievedChunk | None]", replaced: "list[chat.SnapshotPassage | None]" = ()
) -> list[ChatSource | None]:
    """A missing chunk is a replaced source when the snapshot kept its passage (M33): page and paper, no box."""
    fallbacks = list(replaced) or [None] * len(chunks)
    sources: list[ChatSource | None] = []
    for i, (c, kept) in enumerate(zip(chunks, fallbacks), start=1):
        if c is not None:
            sources.append(
                ChatSource(
                    label=f"C{i}",
                    chunk_id=c.id,
                    paper_id=c.paper_id,
                    page=c.page,
                    section=c.section,
                    bbox=c.bbox,
                    from_abstract=c.from_abstract,
                    replaced=False,
                )
            )
        elif kept is not None:
            sources.append(
                ChatSource(
                    label=f"C{i}",
                    chunk_id=None,
                    paper_id=kept.paper_id,
                    page=kept.page,
                    section=kept.section,
                    bbox=None,
                    from_abstract=kept.from_abstract,
                    replaced=True,
                )
            )
        else:
            sources.append(None)
    return sources


def to_provenance(view: "answer_provenance.AnswerProvenance") -> AnswerProvenanceOut:
    return AnswerProvenanceOut(
        model=view.model,
        connection_name=view.connection_name,
        prompt_version=view.prompt_version,
        skill_label=view.skill_label,
        lens=view.lens,
        created_at=view.created_at,
        out_of_date=view.out_of_date,
        passages=[
            AnswerPassageOut(
                label=p.label,
                paper_id=p.paper_id,
                paper_title=p.paper_title,
                page=p.page,
                section=p.section,
                text=p.text,
                state=p.state,
            )
            for p in view.passages
        ],
    )


def to_notes(notes: "list[chat.NoteSource | None]") -> list[NoteSource | None]:
    return [
        None
        if n is None
        else NoteSource(label=f"N{i}", note_id=n.id, paper_id=n.paper_id, page=n.page, provenance=n.provenance)
        for i, n in enumerate(notes, start=1)
    ]


class ChartAnswerCreated(BaseModel):
    output_id: uuid.UUID
