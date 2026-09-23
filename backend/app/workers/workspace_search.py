import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import settings
from app.core import discovery, paper_sources
from app.core.workspace_search import get_run, search_batch
from app.db import SessionLocal
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchRun
from app.providers import discovery_fake

logger = logging.getLogger(__name__)


async def run_workspace_search(ctx: dict, run_id: str) -> None:
    """ARQ job: pages a search run's sources, one search_batch() call per iteration, until every source is
    exhausted or the run's status stops being "running" (checked fresh from the DB each iteration, so a
    concurrent stop-run call is noticed). ctx["transport"] is a test's MockTransport."""
    rid = uuid.UUID(run_id)
    async with SessionLocal() as session:
        try:
            run = await get_run(session, rid)
            if run.status != "running":
                return  # already stopped before this job ran — nothing to do

            sources = await paper_sources.get(session)
            transport = ctx.get("transport")
            if transport is None and settings.discovery_provider == "fake":
                transport = discovery_fake.transport()
            providers = discovery.build_providers(sources, transport)
            try:
                while True:
                    await session.refresh(run)
                    if run.status != "running":
                        break
                    await search_batch(session, providers, run)
                    await session.commit()
                    cursors = (
                        (
                            await session.execute(
                                select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if cursors and all(c.exhausted for c in cursors):
                        run.status = "exhausted"
                        run.stopped_at = datetime.now(timezone.utc)
                        await session.commit()
                        break
            finally:
                await providers.aclose()
        except Exception:
            logger.exception("workspace search run %s failed", rid)
            await session.rollback()
            await session.execute(
                update(WorkspaceSearchRun).where(WorkspaceSearchRun.id == rid).values(status="failed")
            )
            await session.commit()
