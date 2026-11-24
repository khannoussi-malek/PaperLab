"""Rebuilding a package's screening record on import: checking its references, then its runs, hits and cursors."""

import logging
import uuid
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.search import prisma_export
from app.core.search.batch_fetch import _find_or_create_external_ref
from app.core.search.candidates import normal_title
from app.core.workspaces.workspace_package_screening import CURSOR_STATE, STATS_KEYS, UNIQUE_IDS
from app.domain.candidates import Candidate
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace_search import (
    SearchRunEligibility,
    WorkspaceSearchCursor,
    WorkspaceSearchHit,
    WorkspaceSearchRun,
)

logger = logging.getLogger(__name__)

SHARED_TOTALS = (
    "identified",
    "identified_databases",
    "duplicates_removed",
    "stage1_screened",
    "stage1_excluded",
    "stage1_excluded_by_reason",
    "sought",
    "citation_searching",
)  # decided by the hits' own rows: checked whatever the package holds
RETRIEVAL_TOTALS = (
    "not_retrieved",
    "stage2_assessed",
    "stage2_excluded",
    "stage2_excluded_by_reason",
    "included",
)  # decided by the full text: checked only when every retrieved paper has its PDF here


def is_v2(screening: dict) -> bool:
    return "version" in screening


def _keys(rows: list[dict], what: str) -> set[str]:
    keys = [row["key"] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"a {what} key is repeated")
    return set(keys)


def _named(value: str | None, keys: set[str], *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if value not in keys:
        raise ValueError(f"{value!r} is not a key the package holds")


def check_references(doc: dict, paper_keys: set[str]) -> None:
    """Every key the screening names is a key the package holds, and every branch names exactly one target. A
    ValueError otherwise: the import refuses the package as package_invalid."""
    runs, hits = _keys(doc["runs"], "run"), _keys(doc["hits"], "hit")
    for run in doc["runs"]:
        for seed in _seeds(run):
            if not all(v is None or isinstance(v, str) for v in (seed.get("hit"), seed.get("paper"))):
                raise ValueError("a snowball seed names a non-string key")
    for link in doc["links"]:
        if link["parent_hit"] is not None and link["parent_hit"] == link["child_hit"]:
            raise ValueError("a hit links to itself")
    for hit in doc["hits"]:
        _named(hit["run"], runs)
        _named(hit["paper"], paper_keys, optional=True)
        _named(hit["seed_paper"], paper_keys, optional=True)
    for row in doc["eligibility"]:
        _named(row["paper"], paper_keys)
        _named(row["run"], runs)
    for link in doc["links"]:
        _named(link["child_hit"], hits)
        _named(link["parent_hit"], hits, optional=True)
        _named(link["parent_paper"], paper_keys, optional=True)
        _named(link["run"], runs)
    for branch in doc["branches"]:
        if (branch["hit"] is None) == (branch["paper"] is None):
            raise ValueError("a branch names one hit or one paper")
        _named(branch["hit"], hits, optional=True)
        _named(branch["paper"], paper_keys, optional=True)


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _candidate(hit: dict) -> Candidate:
    return Candidate(
        title=hit["title"], authors=list(hit["authors"] or []), year=hit["year"], venue=hit["venue"],
        doi=hit["doi"], abstract=hit["abstract"], external_ids=dict(hit["external_ids"] or {}),
        source_type=hit["source_type"], published_doi=hit["published_doi"], published_venue=hit["published_venue"],
    )  # fmt: skip


def _seeds(run: dict) -> list[dict]:
    """A run's snowball seeds as the package has them. A ValueError when they are not a list of objects."""
    snowball = run["stats"].get("snowball")
    if snowball is None:
        return []
    seeds = snowball.get("seeds", []) if isinstance(snowball, dict) else None
    if not isinstance(seeds, list) or not all(isinstance(seed, dict) for seed in seeds):
        raise ValueError("a run's snowball seeds are malformed")
    return seeds


def _stats_in(stats: dict, hit_ids: dict[str, uuid.UUID]) -> dict:
    """A run's known stats with fresh seed ids; a seed's hit is its rebuilt hit's id (or None when it has none)."""
    kept = {k: v for k, v in stats.items() if k in STATS_KEYS}
    snowball = kept.get("snowball")
    if snowball is None:
        return kept
    seeds = []
    for seed in snowball.get("seeds", []):
        hit = hit_ids.get(seed.get("hit"))
        rest = {k: v for k, v in seed.items() if k not in ("id", "hit", "paper", "hit_id")}
        seeds.append(rest | {"id": str(uuid.uuid4()), "hit_id": str(hit) if hit else None})
    return kept | {"snowball": {**snowball, "seeds": seeds}}


def _fresh_copy(session, candidate: Candidate) -> ExternalRef:
    """A reference for a hit whose library reference an earlier hit of this import already uses. It keeps the title,
    DOI and bibliographic fields but not the unique-indexed external ids, which the first reference owns."""
    ref = ExternalRef(
        title=candidate.title, doi=candidate.doi, authors=candidate.authors, year=candidate.year, venue=candidate.venue,
        external_ids={k: v for k, v in candidate.external_ids.items() if k not in UNIQUE_IDS},
    )  # fmt: skip
    session.add(ref)
    return ref


async def _reference(session, hit: dict, used: set[uuid.UUID]) -> ExternalRef:
    """The hit's library reference. The import only reads an existing one (M1); when an earlier hit of this import
    already uses it, the hit gets its own copy, so both hits are kept and the counts still match (M4)."""
    candidate = _candidate(hit)
    ref = await _find_or_create_external_ref(session, candidate, backfill=False)
    if ref.id in used:
        ref = _fresh_copy(session, candidate)
        await session.flush()
    used.add(ref.id)
    return ref


async def _place_hit(session, workspace_id, hit, run_ids, paper_ids, hit_ids, used) -> uuid.UUID | None:
    """One hit with its reference found or created. None only if the insert conflicts, which the copies above rule out;
    the count check would then refuse the package."""
    ref = await _reference(session, hit, used)
    ai, stage1 = hit["ai_suggestion"] or {}, hit["stage1"]
    row = {
        "id": hit_ids[hit["key"]], "workspace_id": workspace_id, "run_id": run_ids[hit["run"]],
        "external_ref_id": ref.id, "source_method": hit["source_method"],
        "seed_paper_id": paper_ids.get(hit["seed_paper"]), "snowball_round": hit["snowball_round"],
        "normalized_title": normal_title(hit["title"]), "first_seen_at": _when(hit["first_seen_at"]),
        "stage1_status": stage1["status"], "stage1_exclude_reason": stage1["exclude_reason"],
        "stage1_note": stage1["note"], "stage1_decided_at": _when(hit["stage1_decided_at"]),
        "priority": hit["priority"], "topic_fit": hit["topic_fit"], "acquisition_status": hit["acquisition_status"],
        "paper_id": paper_ids.get(hit["paper"]), "suggestion": ai.get("suggestion"),
        "suggestion_reason": ai.get("reason"), "suggestion_note": ai.get("note"), "suggestion_model": ai.get("model"),
        "suggestion_relevance": ai.get("relevance"), "suggestion_confidence": ai.get("confidence"),
        "suggestion_quotes": ai.get("quotes"), "suggestion_flags": ai.get("flags"),
        "suggestion_prompt_version": ai.get("prompt_version"), "suggested_at": _when(ai.get("suggested_at")),
    }  # fmt: skip
    return await session.scalar(
        pg_insert(WorkspaceSearchHit)
        .values(row)
        .on_conflict_do_nothing(index_elements=["workspace_id", "external_ref_id"])
        .returning(WorkspaceSearchHit.id)
    )


def _cursor_rows(runs: list[dict], run_ids: dict[str, uuid.UUID]) -> list[dict]:
    return [
        {
            "run_id": run_ids[run["key"]],
            "source": c["source"],
            "cursor_json": {k: v for k, v in c["cursor"].items() if k in CURSOR_STATE},
            "exhausted": True,
            "last_error": c["last_error"],
        }
        for run in runs
        for c in run["cursors"]
    ]


async def rebuild(session, doc: dict, workspace, paper_ids: dict[str, uuid.UUID]) -> int:
    """Adds the package's screening to `workspace` (flushed; its papers are in `paper_ids`, every key the package
    holds). Rows only: the caller owns the commit. Returns the number of search results (hits) rebuilt."""
    workspace.screening_ranked_used = doc["workspace"]["screening_ranked_used"]
    workspace.screening_criteria = doc["workspace"]["screening_criteria"]
    run_ids = {run["key"]: uuid.uuid4() for run in doc["runs"]}
    hit_ids = {hit["key"]: uuid.uuid4() for hit in doc["hits"]}
    for run in doc["runs"]:
        session.add(WorkspaceSearchRun(
            id=run_ids[run["key"]], workspace_id=workspace.id, query_text=run["query"],
            query_overrides_json=run["query_overrides"] or {}, filters_json=run["filters"],
            sources_json=run["sources"], status="exhausted", started_at=_when(run["started_at"]),
            stopped_at=_when(run["stopped_at"]), stats_json=_stats_in(run["stats"], hit_ids),
        ))  # fmt: skip
    await session.flush()
    if cursors := _cursor_rows(doc["runs"], run_ids):
        await session.execute(pg_insert(WorkspaceSearchCursor).values(cursors).on_conflict_do_nothing())
    placed: dict[str, uuid.UUID] = {}
    used: set[uuid.UUID] = set()
    for hit in doc["hits"]:
        if (new_id := await _place_hit(session, workspace.id, hit, run_ids, paper_ids, hit_ids, used)) is not None:
            placed[hit["key"]] = new_id
    await session.flush()
    await _insert_rows(
        session,
        SearchRunEligibility,
        [
            {
                "paper_id": paper_ids[row["paper"]],
                "search_run_id": run_ids[row["run"]],
                "stage2_status": row["stage2_status"],
                "stage2_exclude_reason": row["exclude_reason"],
                "assessed_at": _when(row["assessed_at"]),
            }
            for row in doc["eligibility"]
        ],
    )
    await _insert_rows(
        session,
        WorkspaceHitLink,
        [
            {
                "workspace_id": workspace.id,
                "child_hit_id": placed[link["child_hit"]],
                "parent_hit_id": placed.get(link["parent_hit"]),
                "parent_paper_id": paper_ids.get(link["parent_paper"]),
                "run_id": run_ids[link["run"]],
                "kind": link["kind"],
            }
            for link in doc["links"]
            if link["child_hit"] in placed and (link["parent_hit"] is None or link["parent_hit"] in placed)
        ],
    )
    await _insert_rows(
        session,
        WorkspaceBranchState,
        [
            {
                "workspace_id": workspace.id,
                "hit_id": placed.get(b["hit"]) if b["hit"] else None,
                "paper_id": paper_ids.get(b["paper"]) if b["paper"] else None,
                "state": b["state"],
                "directions": b["directions"] or [],
                "reason": b["reason"],
                "set_by": b["set_by"],
            }
            for b in doc["branches"]
            if (placed.get(b["hit"]) if b["hit"] else paper_ids.get(b["paper"])) is not None
        ],
    )
    return len(placed)


async def _insert_rows(session, model, rows: list[dict]) -> None:
    if rows:
        await session.execute(pg_insert(model).values(rows).on_conflict_do_nothing())


def full_text_in_package(screening: dict, papers_rows: list[dict]) -> bool:
    """True when the package carries the PDF of every retrieved hit's paper, so the full-text totals can be reproduced
    here. Decided from the package alone (papers.json and screening.json), never from what this library holds (M3)."""
    has_pdf = {row["key"]: bool(row.get("pdf")) for row in papers_rows}
    return all(
        has_pdf[hit["paper"]]
        for hit in screening["hits"]
        if hit["stage1"]["status"] == "relevant"
        and hit["acquisition_status"] in prisma_export.RETRIEVED
        and hit["paper"] is not None
    )


async def counts_match(session, workspace_id: uuid.UUID, expected: dict, full_text: bool) -> bool:
    """True when prisma_export on the rebuilt workspace gives the package's numeric totals (see SHARED_TOTALS and
    RETRIEVAL_TOTALS; the latter only when `full_text`). Flush first: prisma_export reads what this session has
    written. Any failure to read the rebuilt screening back is a mismatch, never a server error."""
    try:
        actual = asdict(await prisma_export.prisma_export(session, workspace_id, None))
    except Exception:
        logger.warning("the rebuilt screening of %s could not be counted", workspace_id, exc_info=True)
        return False
    # The full-text totals are compared only when the package carried every retrieved PDF AND they all ended up here.
    # A paper the library already held without its PDF keeps none (an import never changes a matched paper), so its
    # retrieval count differs for a reason that isn't a broken package: skip, never refuse.
    if full_text and await _retrieved_without_pdf(session, workspace_id):
        full_text = False
    fields = SHARED_TOTALS + (RETRIEVAL_TOTALS if full_text else ())
    return all(actual[name] == expected[name] for name in fields)


async def _retrieved_without_pdf(session, workspace_id: uuid.UUID) -> bool:
    """Whether a retrieved, relevant hit of this workspace points at a paper with no PDF on this library's side."""
    missing = await session.scalar(
        select(func.count())
        .select_from(WorkspaceSearchHit)
        .join(Paper, Paper.id == WorkspaceSearchHit.paper_id)
        .where(
            WorkspaceSearchHit.workspace_id == workspace_id,
            WorkspaceSearchHit.stage1_status == "relevant",
            WorkspaceSearchHit.acquisition_status.in_(prisma_export.RETRIEVED),
            Paper.file_path.is_(None),
        )
    )
    return bool(missing)
