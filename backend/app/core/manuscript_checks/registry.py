"""Every manuscript check, in the order the panel shows them. A new check family is one module plus one line here."""

import logging
from dataclasses import dataclass

from app.core.errors import InvalidInput
from app.core.manuscript_checks import citations, latex_hygiene, references, wording
from app.core.manuscript_checks.base import SEVERITIES, Check, CheckContext, Cost, Finding

logger = logging.getLogger(__name__)

REGISTRY: tuple[Check, ...] = (
    *citations.CHECKS,
    *wording.CHECKS,
    *latex_hygiene.CHECKS,
    *references.CHECKS,
)  # later checks add one line each


@dataclass(frozen=True)
class CheckRun:
    ran: list[str]
    findings: list[Finding]
    counts: dict[str, int]


def select(
    names: list[str] | None = None,
    cost: Cost | None = None,
    registry: tuple[Check, ...] = REGISTRY,
) -> list[Check]:
    known = {c.name for c in registry}
    unknown = sorted(set(names or []) - known)
    if unknown:
        # DomainError(message, **details)
        raise InvalidInput("unknown_check", unknown=unknown, available=[c.name for c in registry])
    return [c for c in registry if (names is None or c.name in names) and (cost in (None, "full") or c.cost == cost)]


def _crash(name: str, exc_name: str) -> Finding:
    return Finding(name, "error", None, None, f"This check crashed: {exc_name}",
                   "Tell the PaperLab maintainers; the other checks still ran.")


def _run_one(check: Check, ctx: CheckContext) -> list[Finding]:
    try:
        found = check.run(ctx)
        for x in found:
            if x.check != check.name or x.severity not in SEVERITIES:
                raise ValueError(f"bad finding from {check.name}")
        return found
    except Exception as exc:
        logger.exception("manuscript check %s crashed", check.name)
        return [_crash(check.name, type(exc).__name__)]


def _key(x: Finding):
    return (SEVERITIES.index(x.severity), x.file is None, x.file or "", x.line is None, x.line or 0, x.check, x.message)


def run_selected(ctx: CheckContext, checks: list[Check]) -> CheckRun:
    findings = sorted((x for c in checks for x in _run_one(c, ctx)), key=_key)
    counts = {s: sum(1 for x in findings if x.severity == s) for s in SEVERITIES}
    return CheckRun([c.name for c in checks], findings, counts)
