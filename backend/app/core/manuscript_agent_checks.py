"""Run a manuscript's checks for an outside agent (the MCP): the findings, capped so one noisy check cannot flood it."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manuscript_checks import service
from app.core.manuscript_checks.base import Finding

MAX_FINDINGS = 200


@dataclass(frozen=True)
class CheckReport:
    ran: list[str]
    findings: list[Finding]
    counts: dict[str, int]  # of every finding, before the cap
    truncated: int


async def check_manuscript(session: AsyncSession, mid: uuid.UUID, names: list[str] | None) -> CheckReport:
    run = await service.run_checks(session, mid, names or None)  # [] means all, like None
    return CheckReport(run.ran, run.findings[:MAX_FINDINGS], run.counts, max(0, len(run.findings) - MAX_FINDINGS))
