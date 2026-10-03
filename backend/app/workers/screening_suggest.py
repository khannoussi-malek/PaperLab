"""ARQ job: one local-model suggestion per unscreened hit, in ranked order (M31b spec §4.2). Suggest only: it writes
the suggestion columns and the workspace's job state, never stage1_status."""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.core import llm_connections
from app.core.errors import Conflict
from app.core.screening import hit_text, load_pool, suggestion_queue
from app.core.screening_suggest import SYSTEM_PROMPT, Suggestion, build_prompt, parse_reply
from app.db import SessionLocal, engine
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm

logger = logging.getLogger(__name__)

# ~3,000 hits at 1-3 s each on a Mac. Registered as the job's timeout in workers/settings.py; the loop stops itself
# SAFETY_MARGIN earlier, and the button resumes with the hits still left.
SUGGEST_JOB_TIMEOUT = 4 * 3600
SAFETY_MARGIN = 60
_LOCK = text("SELECT pg_try_advisory_lock(:key)")
_UNLOCK = text("SELECT pg_advisory_unlock(:key)")


def _lock_key(workspace_id: uuid.UUID) -> int:
    # A different key space from the search runs' locks: their keys are run ids, these are workspace ids ^ 1.
    return (workspace_id.int ^ 1) & 0x7FFFFFFFFFFFFFFF


async def _suggest_one(llm, criteria: str, hit: WorkspaceSearchHit, ref: ExternalRef | None) -> Suggestion:
    title = ref.title if ref else hit.normalized_title
    prompt = build_prompt(criteria, title, ref.abstract if ref else None)
    try:
        return parse_reply("".join([token async for token in llm.stream(SYSTEM_PROMPT, prompt)]))
    except LLMUnavailable:
        raise
    except LLMError:
        return Suggestion("unsure", None, "model error")


async def suggest_screening(ctx: dict, workspace_id: str) -> None:
    wid = uuid.UUID(workspace_id)
    # The advisory lock is session-level: Postgres ties it to one physical connection, not to our ORM `session`
    # object. But `session`'s own connection can rotate to a *different* pooled connection on every
    # `session.commit()` (the engine checks a connection back out for the next statement, which under real
    # concurrent load — e.g. the frontend polling GET /screening while this job runs — need not be the same one).
    # Taking and releasing the lock through `session` let the lock-holding connection drift away mid-job, leaving
    # the original connection's lock stuck forever once it went idle in the pool — found live on 2026-10-03, a
    # stuck "stopping" job blocking every future suggestion run on the workspace. One dedicated connection, held
    # open for the whole job, keeps lock and unlock on the same physical session no matter how often `session`
    # commits.
    async with engine.connect() as lock_conn:
        async with SessionLocal() as session:
            workspace = await session.get(Workspace, wid)
            if workspace is None or workspace.suggest_status != "running":
                return
            if not await lock_conn.scalar(_LOCK, {"key": _lock_key(wid)}):
                logger.info("suggestions for workspace %s already running elsewhere", wid)
                return
            # End lock_conn's own implicit transaction now: the advisory lock itself isn't transactional (it
            # survives commit/rollback either way), but leaving this open would sit "idle in transaction" for up
            # to SUGGEST_JOB_TIMEOUT, holding back autovacuum the whole time.
            await lock_conn.commit()
            try:
                connection, model = await llm_connections.resolve(session, None)
                llm = build_llm(connection, model.name, transport=ctx.get("transport"))
                label = f"{connection.label} · {model.name}"
                pool = await load_pool(session, wid)
                rows = {hit.id: (hit, ref) for hit, ref in pool.rows}
                deadline = time.monotonic() + SUGGEST_JOB_TIMEOUT - SAFETY_MARGIN
                for hit_id in suggestion_queue(pool):
                    await session.refresh(workspace)
                    if workspace.suggest_status != "running" or time.monotonic() >= deadline:
                        break
                    hit, ref = rows[hit_id]
                    await session.refresh(hit)
                    if hit.stage1_status is not None or hit.suggestion is not None or not hit_text(hit, ref).strip():
                        continue  # decided (or suggested) since the job started
                    suggestion = await _suggest_one(llm, workspace.screening_criteria, hit, ref)
                    hit.suggestion, hit.suggestion_reason = suggestion.verdict, suggestion.reason
                    hit.suggestion_note, hit.suggestion_model = suggestion.note, label
                    hit.suggested_at = datetime.now(timezone.utc)
                    workspace.suggest_done += 1
                    await session.commit()
            except (LLMUnavailable, Conflict) as exc:
                workspace.suggest_error = (
                    "Set up a chat model in Settings first" if isinstance(exc, Conflict) else str(exc)
                )
            except Exception:
                logger.exception("screening suggestions for workspace %s failed", wid)
                await session.rollback()  # a failed flush leaves the session unusable until rolled back
                workspace.suggest_error = "Suggestions stopped after an unexpected error"
            finally:
                # The unlock must run even if this commit fails or is cancelled.
                workspace.suggest_status = "idle"
                try:
                    await session.commit()
                finally:
                    await lock_conn.execute(_UNLOCK, {"key": _lock_key(wid)})
                    await lock_conn.commit()
