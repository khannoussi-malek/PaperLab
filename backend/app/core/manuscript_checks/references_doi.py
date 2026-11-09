"""P01: does each .bib DOI exist at Crossref? Pure given an injected async lookup; never registered (S2P B2)."""

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import httpx

from app.core.enrichment import normalize_doi
from app.core.manuscript_checks.base import CheckContext, Finding, ManuscriptInfo
from app.core.manuscript_checks.references import bib_entries

NAME = "references.doi_resolves"
MAX_DOIS = 100  # the deadline is the real cap: the public pool paces about 1 request a second
DEADLINE_SECONDS = 60.0


@dataclass(frozen=True)
class DoiEntry:
    key: str
    doi: str
    file: str
    line: int


@dataclass(frozen=True)
class DoiCheckResult:
    checked: int      # distinct DOIs Crossref answered for (found or not found)
    not_checked: int  # distinct DOIs over the cap, past the deadline, or whose lookup failed
    findings: list[Finding]


def doi_entries(files: Mapping[str, str]) -> list[DoiEntry]:
    # bib_entries reads only ctx.files
    ctx = CheckContext(files, frozenset(), ManuscriptInfo("", "", "never", None, None, None))
    return [
        DoiEntry(e.key, doi, path, e.line)
        for path, e in bib_entries(ctx)
        if (doi := normalize_doi(e.fields.get("doi", "")))
    ]


async def check_dois(
    entries: list[DoiEntry],
    lookup: Callable[[str], Awaitable[dict | None]],
    *,
    max_dois: int = MAX_DOIS,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> DoiCheckResult:
    distinct = list(dict.fromkeys(e.doi for e in entries))
    answers: dict[str, bool | None] = {}  # True found, False not found, None lookup failed
    for doi in distinct[:max_dois]:
        if deadline is not None and clock() >= deadline:
            break
        try:
            answers[doi] = await lookup(doi) is not None
        except (httpx.HTTPError, ValueError, KeyError):
            answers[doi] = None
    findings = []
    for e in entries:
        if e.doi not in answers or answers[e.doi] is True:
            continue
        if answers[e.doi] is False:
            findings.append(Finding(NAME, "error", e.file, e.line,
                                    f"DOI {e.doi} (entry {e.key}) was not found at Crossref.",
                                    "Check the DOI for typos, or replace the entry with one from your library. "
                                    "A made-up reference often shows up this way."))
        else:
            findings.append(Finding(NAME, "warning", e.file, e.line,
                                    f"Could not check DOI {e.doi} (entry {e.key}): Crossref did not answer.",
                                    "Try again later."))
    checked = sum(1 for v in answers.values() if v is not None)
    return DoiCheckResult(checked, len(distinct) - checked, findings)
