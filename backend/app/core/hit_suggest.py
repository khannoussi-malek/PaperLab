"""The AI pre-screen fit for one search hit, run on request ("Summarise now"). Same prompt, model, criteria and
fields as the queued workspace job; it never writes stage1_status."""

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections, workspace_search, workspaces
from app.core.errors import Conflict
from app.core.pipeline import _refuse_remote
from app.core.screening_suggest import SCREENING_PROMPT_VERSION, suggest
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm

SUGGEST_TIMEOUT = 60  # seconds


async def suggest_one(session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID, *, allow_remote: bool) -> dict:
    await workspaces.require_writable(session, workspace_id)
    hit = await session.get(WorkspaceSearchHit, hit_id)
    await workspace_search.get_hit(session, hit_id, workspace_id)  # NotFound for a missing or foreign hit
    workspace = await session.get(Workspace, workspace_id)
    if not (workspace.research_question or workspace.inclusion_criteria):
        raise Conflict("needs_criteria")
    if workspace.suggest_status != "idle":
        raise Conflict("prescreen_running")
    await _refuse_remote(session, allow_remote)
    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    connection, model = await llm_connections.resolve(session, None)
    llm = build_llm(connection, model.name)
    try:
        async with asyncio.timeout(SUGGEST_TIMEOUT):
            result = await suggest(
                llm, workspace.research_question, workspace.inclusion_criteria, workspace.exclusion_criteria,
                ref.title if ref else hit.normalized_title, ref.abstract if ref else None,
            )
    except TimeoutError as exc:
        raise Conflict("suggest_timeout") from exc
    except (LLMUnavailable, LLMError) as exc:
        raise Conflict("model_unavailable", detail=str(exc)) from exc
    hit.suggestion, hit.suggestion_reason, hit.suggestion_note = result.verdict, result.reason, result.note
    hit.suggestion_model = None if "no_abstract" in result.flags else f"{connection.label} · {model.name}"
    hit.suggestion_relevance, hit.suggestion_quotes = result.relevance, result.quotes
    hit.suggestion_confidence, hit.suggestion_flags = result.confidence, result.flags
    hit.suggestion_prompt_version = SCREENING_PROMPT_VERSION
    hit.suggested_at = datetime.now(timezone.utc)
    await session.commit()
    return await workspace_search.get_hit(session, hit_id, workspace_id)
