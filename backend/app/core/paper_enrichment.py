"""M61 enrich_papers: gives library papers that are the arXiv copy of a published paper their published version
(venue, DOI, peer review) from Semantic Scholar's batch endpoint. Only on an explicit call. Never writes the paper's
own doi, venue, files or status, and never a field the owner edited by hand (manual_fields)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.candidates import s2_triage
from app.core.enrichment import normalize_doi, openalex_published
from app.core.hit_enrichment import CHUNK, batch_with_backoff
from app.core.source_types import ARXIV_DOI_PREFIX, is_preprint_copy, peer_reviewed_of
from app.models.paper import Paper
from app.models.workspace import workspace_papers
from app.providers import openalex

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperEnrichResult:
    looked_up: int = 0
    filled: int = 0
    not_found: int = 0
    remaining: int = 0
    rate_limited: bool = False


async def _unchecked(session: AsyncSession, ws: uuid.UUID) -> list[Paper]:
    query = (
        select(Paper)
        .join(workspace_papers, workspace_papers.c.paper_id == Paper.id)
        .where(workspace_papers.c.workspace_id == ws, Paper.published_checked_at.is_(None))
        .order_by(Paper.id)
    )
    return list((await session.execute(query)).scalars())


async def papers_to_enrich(session: AsyncSession, ws: uuid.UUID) -> list[Paper]:
    """The workspace's papers Semantic Scholar was not asked about yet and that it can be asked about."""
    return [p for p in await _unchecked(session, ws) if s2_id(p)]


def s2_id(paper: Paper) -> str | None:
    """"ARXIV:<id>" for an arXiv-issued DOI, "DOI:<doi>" for any other, else None (no arXiv id column exists)."""
    doi = (paper.doi or "").strip()
    if not doi:
        return None
    if doi.lower().startswith(ARXIV_DOI_PREFIX):
        return f"ARXIV:{doi[len(ARXIV_DOI_PREFIX):]}"
    return f"DOI:{doi}"


def apply_s2(paper: Paper, answer: dict) -> bool:
    """Fills from an S2 paper; fields in manual_fields are skipped (a hand-set source_type also blocks peer_reviewed).
    Any paper: source_type when empty, peer_reviewed "true" when "unknown" and the type is peer-reviewed. A preprint
    copy (arXiv DOI or source_type "preprint") also gets published_doi and published_venue (never its own DOI), and
    peer_reviewed "true" even over "false". peer_reviewed is never lowered. True when anything changed."""
    source_type, published_doi, published_venue = s2_triage(answer)
    preprint = is_preprint_copy(paper)
    if published_doi and published_doi == normalize_doi(paper.doi or ""):
        published_doi = None  # the paper's own DOI is not its published version's
    if preprint and not (published_doi or published_venue):
        return False  # an arXiv-only answer: nothing to learn
    found: dict[str, str | None] = {}
    if preprint:
        found |= {"published_doi": published_doi, "published_venue": published_venue}
    if not paper.source_type:
        found["source_type"] = source_type
    peer = peer_reviewed_of(source_type) == "true"
    if peer and (preprint or paper.peer_reviewed == "unknown") and "source_type" not in paper.manual_fields:
        found["peer_reviewed"] = "true"
    changed = False
    for field, value in found.items():
        if value and field not in paper.manual_fields and getattr(paper, field) != value:
            setattr(paper, field, value)
            changed = True
    return changed


def apply_openalex(paper: Paper, work: dict) -> bool:
    """A preprint copy's OpenAlex work that is its published version: same write rules as apply_s2."""
    doi, venue, _ = openalex_published(work)
    if not is_preprint_copy(paper) or doi in (None, normalize_doi(paper.doi or "")):
        return False
    found = {"published_doi": doi, "published_venue": venue}
    if "source_type" not in paper.manual_fields:
        found["peer_reviewed"] = "true"
    changed = False
    for field, value in found.items():
        if value and field not in paper.manual_fields and getattr(paper, field) != value:
            setattr(paper, field, value)
            changed = True
    return changed


async def _openalex_pass(session: AsyncSession, oa: httpx.AsyncClient, ws: uuid.UUID) -> int:
    """After S2: preprint copies with an openalex_id and still no published_doi, 50 per request. A failing
    request is logged and skipped. Returns how many papers were filled."""
    query = (
        select(Paper)
        .join(workspace_papers, workspace_papers.c.paper_id == Paper.id)
        .where(workspace_papers.c.workspace_id == ws, Paper.openalex_id.is_not(None), Paper.published_doi.is_(None))
        .order_by(Paper.id)
    )
    papers = [p for p in (await session.execute(query.execution_options(populate_existing=True))).scalars()
              if is_preprint_copy(p)]  # fmt: skip
    try:
        works = await openalex.works_by_ids(oa, [p.openalex_id for p in papers])
    except httpx.HTTPError:
        logger.exception("OpenAlex batch for %d papers failed; going on", len(papers))
        return 0
    by_id = {w["id"].rsplit("/", 1)[-1]: w for w in works}
    filled = sum(apply_openalex(p, by_id[p.openalex_id]) for p in papers if p.openalex_id in by_id)
    await session.commit()
    return filled


async def enrich(
    session: AsyncSession, http: httpx.AsyncClient, ws: uuid.UUID, oa: httpx.AsyncClient | None = None
) -> PaperEnrichResult:
    """Looks the papers up in chunks of CHUNK, one batch call each, committing per chunk. A chunk that fails is
    logged and counted as not found; four 429s in a row stop the job, with the count of papers left."""
    pending = await _unchecked(session, ws)
    papers = [(p, key) for p in pending if (key := s2_id(p))]
    for paper in pending:
        if not s2_id(paper):
            paper.published_checked_at = datetime.now(timezone.utc)  # nothing to ask about: never picked again
    await session.commit()
    looked_up = filled = not_found = 0
    for start in range(0, len(papers), CHUNK):
        chunk = papers[start : start + CHUNK]
        try:
            answers = await batch_with_backoff(http, [key for _, key in chunk])
            if answers is not None and len(answers) != len(chunk):
                raise httpx.DecodingError(f"S2 answered {len(answers)} papers for {len(chunk)} ids")
        except httpx.HTTPError:
            logger.exception("Semantic Scholar batch of %d papers failed; going on", len(chunk))
            not_found += len(chunk)
            continue
        if answers is None:
            remaining = len(papers) - start
            logger.warning("Semantic Scholar kept answering 429; stopping with %d papers left", remaining)
            return PaperEnrichResult(looked_up, filled, not_found, remaining, True)
        looked_up += len(chunk)
        # The batch (and any 429 wait) can take long: re-read the papers so a hand edit made meanwhile is seen.
        ids = [paper.id for paper, _ in chunk]
        await session.execute(select(Paper).where(Paper.id.in_(ids)).execution_options(populate_existing=True))
        asked_at = datetime.now(timezone.utc)
        for (paper, _), answer in zip(chunk, answers, strict=True):
            paper.published_checked_at = asked_at
            if answer is None:
                not_found += 1
            elif apply_s2(paper, answer):
                filled += 1
        await session.commit()
    if oa is not None:
        filled += await _openalex_pass(session, oa, ws)
    return PaperEnrichResult(looked_up, filled, not_found)
