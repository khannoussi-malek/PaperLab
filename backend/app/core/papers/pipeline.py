"""What Claude does over MCP (M39 F1): each function backs one tool, composing existing core services.

Workspaces come by name (D93). Jobs go through `queue`, paper sources through `discovery.open_providers`. No SQL here:
every read and write is an existing service's. Results are the API's own schemas, so Claude and the app see the same
fields.
"""

import uuid
from dataclasses import dataclass, fields
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import claims, claims_batch
from app.core.citations import citations_export
from app.core.notes import evidence_card_views, evidence_cards, notes
from app.core.papers import papers
from app.core.search import (
    saved_searches,
    schedules,
    screening,
)
from app.core.workspaces import tags, workspaces
from app.domain.errors import Conflict, InvalidInput
from app.providers.base import LLMError, LLMUnavailable
from app.schemas.papers import PaperOut

workspace_id = workspaces.by_name


@dataclass(frozen=True)
class Removed:
    workspace: str
    paper_id: uuid.UUID
    removed: bool = True


async def list_papers(
    session: AsyncSession,
    workspace: str,
    tags_: list[str] | None = None,
    match: Literal["any", "all"] = "any",
    full_text: bool | None = None,
) -> list[PaperOut]:
    ws = await workspace_id(session, workspace)
    rows = await workspaces.papers(session, ws)
    wanted = await tags.paper_ids(session, ws, tags_, match)
    return [
        PaperOut.model_validate(row)
        for row in rows
        if (wanted is None or row.id in wanted)
        and (full_text is None or (row.evidence_access == "full_text") == full_text)
    ]


async def list_tags(session: AsyncSession, workspace: str) -> list[tags.TagSummary]:
    return await tags.summaries(session, await workspace_id(session, workspace))


async def tag_papers(
    session: AsyncSession, workspace: str, tag: str, paper_ids: list[uuid.UUID] | None, dois: list[str] | None
) -> tags.TagResult:
    return await tags.tag_papers(session, await workspace_id(session, workspace), tag, paper_ids or (), dois or ())


async def untag_papers(
    session: AsyncSession, workspace: str, tag: str, paper_ids: list[uuid.UUID] | None, dois: list[str] | None
) -> tags.TagResult:
    return await tags.untag_papers(session, await workspace_id(session, workspace), tag, paper_ids or (), dois or ())


@dataclass(frozen=True)
class TagRenamed:
    old: str
    new: str


@dataclass(frozen=True)
class TagDeleted:
    tag: str
    papers: int


async def rename_tag(session: AsyncSession, workspace: str, tag: str, new_name: str) -> TagRenamed:
    ws = await workspace_id(session, workspace)
    (found,) = await tags.resolve(session, ws, [tag])
    old = found.name
    return TagRenamed(old, await tags.rename(session, ws, tag, new_name))


async def delete_tag(session: AsyncSession, workspace: str, tag: str) -> TagDeleted:
    ws = await workspace_id(session, workspace)
    (found,) = await tags.resolve(session, ws, [tag])
    name = found.name
    return TagDeleted(name, await tags.delete(session, ws, tag))


async def add_paper_to_workspace(session: AsyncSession, workspace: str, paper_id: uuid.UUID) -> PaperOut:
    await workspaces.add_paper(session, await workspace_id(session, workspace), paper_id)
    return PaperOut.model_validate(await papers.get_paper(session, paper_id))


async def remove_paper_from_workspace(session: AsyncSession, workspace: str, paper_id: uuid.UUID) -> Removed:
    await workspaces.remove_paper(session, await workspace_id(session, workspace), paper_id)
    return Removed(workspace=workspace.strip(), paper_id=paper_id)


async def _refuse_remote(session: AsyncSession, allow_remote: bool) -> None:
    """There is no confirm dialog over MCP: a remote default model runs only when the caller says the owner agreed."""
    model = await screening._default_model(session)
    if model is not None and not model[1] and not allow_remote:
        raise Conflict("remote_model_needs_confirm", model=model[0], host=model[2])


AUTHORS = {"you": {"human"}, "ai": {"llm", "llm_edited"}, "all": {"human", "llm", "llm_edited"}}
LABELS = {"human": "You", "llm": "AI", "llm_edited": "AI · edited"}


@dataclass(frozen=True)
class LabelledNote(notes.NoteView):
    author: str = ""


async def list_notes(
    session: AsyncSession, workspace: str | None = None, paper_id: uuid.UUID | None = None, author: str = "all",
    tags_: list[str] | None = None, match: Literal["any", "all"] = "any",
) -> list[LabelledNote]:
    if (workspace is None) == (paper_id is None):
        raise InvalidInput("notes_scope", hint="Give either workspace or paper_id.")
    if tags_ and workspace is None:
        raise InvalidInput("tags_need_a_workspace")
    if author not in AUTHORS:
        raise InvalidInput(f"author is one of {', '.join(AUTHORS)}")
    wanted = None
    if workspace is not None:
        ws = await workspace_id(session, workspace)
        wanted = await tags.paper_ids(session, ws, tags_, match)
        views = await workspaces.notes(session, ws)
    else:
        views = await notes.list_notes_for_paper(session, paper_id)
    return [
        LabelledNote(**{f.name: getattr(v, f.name) for f in fields(v)}, author=LABELS[v.provenance])
        for v in views
        if v.provenance in AUTHORS[author] and (wanted is None or wanted.intersection(v.paper_ids))
    ]


@dataclass(frozen=True)
class SavedSearchRequest:
    """A saved search as the MCP tool asks for it: daily or weekly at `time` (weekday 0 = Sunday), or a cron."""

    query: str
    schedule: str = "daily"
    time: str | None = "02:00"
    weekday: int | None = None
    cron: str | None = None
    sources: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    timezone: str = "UTC"


async def create_saved_search(
    session: AsyncSession, workspace: str, request: SavedSearchRequest
) -> saved_searches.SavedSearchView:
    ws = await workspace_id(session, workspace)
    r = request
    if (r.cron is not None and r.schedule != "cron") or (r.weekday is not None and r.schedule != "weekly"):
        raise InvalidInput("invalid_schedule", hint="cron needs schedule='cron'; weekday needs schedule='weekly'.")
    expression = schedules.to_cron(r.schedule, time=r.time, weekday=r.weekday, cron=r.cron)
    spec = saved_searches.SavedSearchSpec(
        query=r.query, schedule=expression, timezone=r.timezone, sources=r.sources or [], year_from=r.year_from,
        year_to=r.year_to,
    )
    return await saved_searches.create(session, ws, spec)


async def list_saved_searches(session: AsyncSession, workspace: str) -> list[saved_searches.SavedSearchView]:
    return await saved_searches.list_for_workspace(session, await workspace_id(session, workspace))


async def set_saved_search_enabled(
    session: AsyncSession, saved_search_id: uuid.UUID, enabled: bool
) -> saved_searches.SavedSearchView:
    view = await saved_searches.get(session, saved_search_id)
    return await saved_searches.update(session, view.workspace_id, saved_search_id, {"enabled": enabled})


async def verify_claim(
    session: AsyncSession, claim: str, paper_id: uuid.UUID | None = None, doi: str | None = None,
    quoted_text: str | None = None, save: bool = False, allow_remote: bool = False,
) -> claims.ClaimCheck:
    await _refuse_remote(session, allow_remote)
    try:
        return await claims.verify_claim(
            session, claim, paper_id=paper_id, doi=doi, quoted_text=quoted_text, save=save
        )
    except (LLMError, LLMUnavailable) as exc:
        raise Conflict("model_unavailable", detail=str(exc)) from exc


async def verify_claims(
    session: AsyncSession, text: str, workspace: str | None = None, save: bool = False, allow_remote: bool = False
) -> list[claims_batch.ClaimItem]:
    ws = await workspace_id(session, workspace) if workspace is not None else None
    await _refuse_remote(session, allow_remote)
    return await claims_batch.verify_claims(session, text, workspace_id=ws, save=save)


@dataclass(frozen=True)
class EvidenceRow:
    paper_id: uuid.UUID
    title: str
    year: int | None
    first_author: str | None
    card: evidence_card_views.CardSummary | None


async def generate_evidence_card(
    session: AsyncSession, paper_id: uuid.UUID, regenerate: bool = False, confirm: bool = False,
    allow_remote: bool = False,
) -> evidence_card_views.CardSummary:
    """Starts the background job and returns the card at once (`generating`); the caller polls get_evidence_card."""
    await _refuse_remote(session, allow_remote)
    [view] = await evidence_cards.request_cards(session, paper_ids=[paper_id], regenerate=regenerate, confirm=confirm)
    return evidence_card_views.summarize(view)


async def get_evidence_card(session: AsyncSession, paper_id: uuid.UUID) -> evidence_card_views.CardSummary:
    return evidence_card_views.summarize(await evidence_card_views.get_card(session, paper_id))


async def list_evidence_cards(
    session: AsyncSession, workspace: str, tags_: list[str] | None = None, match: Literal["any", "all"] = "any"
) -> list[EvidenceRow]:
    ws = await workspace_id(session, workspace)
    wanted = await tags.paper_ids(session, ws, tags_, match)
    rows = await evidence_card_views.workspace_cards(session, ws)
    return [
        EvidenceRow(r.paper_id, r.title, r.year, r.first_author, r.card and evidence_card_views.summarize(r.card))
        for r in rows
        if wanted is None or r.paper_id in wanted
    ]


async def export_citations(
    session: AsyncSession, *, workspace_id: uuid.UUID | None = None, paper_ids: list[uuid.UUID] | None = None,
    fmt: str, notes: bool = False,
) -> tuple[str, int]:  # fmt: skip
    """(text, paper count) for a workspace or a selection of papers; shared by the API and the MCP tool."""
    return await citations_export.export_papers(
        session, workspace_id=workspace_id, paper_ids=paper_ids, fmt=fmt, notes=notes
    )


@dataclass(frozen=True)
class CitationExport:
    format: str
    count: int
    text: str


async def export_citations_as(
    session: AsyncSession, workspace: str, fmt: str, tags_: list[str] | None = None,
    match: Literal["any", "all"] = "any",
) -> CitationExport:
    ws = await workspace_id(session, workspace)
    wanted = await tags.paper_ids(session, ws, tags_, match)
    ids = None if wanted is None else [p.id for p in await workspaces.papers(session, ws) if p.id in wanted]
    text, count = await export_citations(session, workspace_id=ws, paper_ids=ids, fmt=fmt)
    return CitationExport(fmt, count, text)
