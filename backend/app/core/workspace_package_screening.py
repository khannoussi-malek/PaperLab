"""A workspace's live screening as a package carries it (M35c, screening.json version 2): the runs with their stats and
paging state, every hit with its reference, stage-1 decision and AI suggestion, the stage-2 eligibility, the snowball
links and the branch states. Every id leaves as a package key (r1, h1, p1); papers outside the workspace that the
screening names are listed too, marked `member: false`. Nothing secret: a cursor keeps only its paging state, and
stats and last errors pass redact().

The import side (`rebuild`) is added below this export half."""

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import any_, bindparam, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import prisma_export, search_run_results
from app.core.candidates import Candidate, normal_title
from app.core.redact import redact
from app.core.workspace_package_shapes import CursorState, StatsRow
from app.core.workspace_search import _find_or_create_external_ref
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import (
    SearchRunEligibility,
    WorkspaceSearchCursor,
    WorkspaceSearchHit,
    WorkspaceSearchRun,
)

VERSION = 2
CURSOR_STATE = tuple(CursorState.model_fields)  # paging state only; nothing else leaves
STATS_KEYS = tuple(StatsRow.model_fields)  # the stats keys the screening reads; nothing else is imported
UNIQUE_IDS = ("openalex", "semantic_scholar", "biorxiv", "medrxiv", "iacr_eprint")  # unique-indexed external ids
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Live:
    runs: list[WorkspaceSearchRun]
    cursors: dict[uuid.UUID, list[WorkspaceSearchCursor]]
    hits: list[tuple[WorkspaceSearchHit, ExternalRef | None]]  # first seen first
    eligibility: list[SearchRunEligibility]
    links: list[WorkspaceHitLink]
    branches: list[WorkspaceBranchState]


def _iso(moment) -> str | None:
    return moment.isoformat() if moment else None


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _array(ids):
    return bindparam(None, list(ids), type_=ARRAY(PG_UUID(as_uuid=True)))


async def load(session: AsyncSession, workspace_id: uuid.UUID, runs: list[WorkspaceSearchRun]) -> Live:
    """Every screening row of the workspace, read once. `runs` are the workspace's runs, in start order."""
    run_ids = [run.id for run in runs]
    hit_rows = await session.execute(
        select(WorkspaceSearchHit, ExternalRef)
        .outerjoin(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id)
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
    )
    return Live(
        runs=runs,
        cursors=await search_run_results.cursors_by_run(session, run_ids),
        hits=[(hit, ref) for hit, ref in hit_rows.all()],
        eligibility=list(
            (
                await session.scalars(
                    select(SearchRunEligibility).where(SearchRunEligibility.search_run_id.in_(run_ids))
                )
            ).all()
        ),
        links=list(
            (await session.scalars(select(WorkspaceHitLink).where(WorkspaceHitLink.workspace_id == workspace_id))).all()
        ),
        branches=list(
            (
                await session.scalars(
                    select(WorkspaceBranchState).where(WorkspaceBranchState.workspace_id == workspace_id)
                )
            ).all()
        ),
    )


def _seed_papers(live: Live) -> set[uuid.UUID]:
    """The snowball seeds' ids that are not hits: a seed paper (a library paper or a hand-added one)."""
    hit_ids = {hit.id for hit, _ in live.hits}
    seeds = {_uuid((seed or {}).get("id")) for run in live.runs for seed in _seeds_of(run)}
    return {s for s in seeds if s is not None and s not in hit_ids}


def _seeds_of(run: WorkspaceSearchRun) -> list[dict]:
    return ((run.stats_json or {}).get("snowball") or {}).get("seeds", [])


def referenced_papers(live: Live) -> set[uuid.UUID]:
    """Every paper the screening names, members or not: a hit's, a seed's, an eligibility's, a link's, a branch's."""
    ids = {h.paper_id for h, _ in live.hits} | {h.seed_paper_id for h, _ in live.hits}
    ids |= {e.paper_id for e in live.eligibility} | {b.paper_id for b in live.branches}
    ids |= {link.parent_paper_id for link in live.links} | _seed_papers(live)
    return {i for i in ids if i is not None}


async def outside_papers(session: AsyncSession, live: Live, members: set[uuid.UUID]) -> list[Paper]:
    """The referenced papers that are not workspace members, by title. A seed id that names no paper is dropped."""
    wanted = referenced_papers(live) - members
    if not wanted:
        return []
    rows = await session.scalars(select(Paper).where(Paper.id == any_(_array(wanted))))
    return sorted(rows, key=lambda paper: (paper.title or "", str(paper.id)))


def _hit_keys(live: Live) -> dict[uuid.UUID, str]:
    return {hit.id: f"h{number}" for number, (hit, _) in enumerate(live.hits, start=1)}


def _cursor_state(cursor_json: dict | None) -> dict:
    return {k: v for k, v in (cursor_json or {}).items() if k in CURSOR_STATE}


def _seed(seed: dict, hit_keys: dict, paper_keys: dict) -> dict:
    """A seed's line without its database ids: its hit and its paper by key (either may be None). Its error strings
    get the same redaction as a cursor's last error."""
    rest = {k: v for k, v in seed.items() if k not in ("id", "hit_id", "error", "errors")}
    if "error" in seed:
        rest["error"] = search_run_results.short_error(seed["error"])
    if isinstance(seed.get("errors"), dict):
        rest["errors"] = {kind: search_run_results.short_error(text) for kind, text in seed["errors"].items()}
    return rest | {
        "hit": hit_keys.get(_uuid(seed.get("hit_id"))),
        "paper": paper_keys.get(_uuid(seed.get("id"))),
    }


def _stats(stats: dict | None, hit_keys: dict, paper_keys: dict) -> dict:
    out = dict(stats or {})
    if "warnings" in out:
        out["warnings"] = [{**w, "message": redact(str(w.get("message", "")))} for w in out["warnings"]]
    if "snowball" in out:
        snowball = out["snowball"] or {}
        seeds = [_seed(s, hit_keys, paper_keys) for s in snowball.get("seeds", [])]
        out["snowball"] = {**snowball, "seeds": seeds}
    return out


def _run_row(run, run_keys, labels, hit_keys, paper_keys, cursors) -> dict:
    return {
        "key": run_keys[run.id],
        "query": labels[run.id],
        "sources": run.sources_json,
        "filters": run.filters_json,
        "query_overrides": run.query_overrides_json or {},
        "status": run.status,
        "started_at": _iso(run.started_at),
        "stopped_at": _iso(run.stopped_at),
        "stats": _stats(run.stats_json, hit_keys, paper_keys),
        "cursors": [
            {
                "source": c.source,
                "exhausted": c.exhausted,
                "cursor": _cursor_state(c.cursor_json),
                "last_error": search_run_results.short_error(c.last_error),
            }
            for c in sorted(cursors, key=lambda c: c.source)
        ],
    }


def _ai_suggestion(hit: WorkspaceSearchHit) -> dict | None:
    if hit.suggestion is None:
        return None
    return {
        "ai": True,
        "suggestion": hit.suggestion,
        "reason": hit.suggestion_reason,
        "note": hit.suggestion_note,
        "model": hit.suggestion_model,
        "relevance": hit.suggestion_relevance,
        "confidence": hit.suggestion_confidence,
        "quotes": hit.suggestion_quotes,
        "flags": hit.suggestion_flags,
        "prompt_version": hit.suggestion_prompt_version,
        "suggested_at": _iso(hit.suggested_at),
    }


def _hit_row(key, hit, ref, run_keys, paper_keys, stage2) -> dict:
    """The hit with its reference's metadata (a reference gone from the library keeps the hit's own title)."""
    verdict = stage2.get((hit.paper_id, hit.run_id)) if hit.paper_id else None
    return {
        "key": key, "run": run_keys[hit.run_id],
        "title": ref.title if ref else hit.normalized_title, "doi": ref.doi if ref else None,
        "external_ids": (ref.external_ids if ref else None) or {}, "authors": (ref.authors if ref else None) or [],
        "year": ref.year if ref else None, "venue": ref.venue if ref else None,
        "abstract": ref.abstract if ref else None, "source_type": ref.source_type if ref else None,
        "published_doi": ref.published_doi if ref else None, "published_venue": ref.published_venue if ref else None,
        "paper": paper_keys.get(hit.paper_id), "source_method": hit.source_method,
        "seed_paper": paper_keys.get(hit.seed_paper_id), "snowball_round": hit.snowball_round,
        "first_seen_at": _iso(hit.first_seen_at), "acquisition_status": hit.acquisition_status,
        "priority": hit.priority, "topic_fit": hit.topic_fit,
        "stage1": {"status": hit.stage1_status, "exclude_reason": hit.stage1_exclude_reason, "note": hit.stage1_note},
        "stage1_decided_at": _iso(hit.stage1_decided_at),
        "stage2": {"status": verdict.stage2_status, "exclude_reason": verdict.stage2_exclude_reason}
        if verdict is not None else None,
        "ai_suggestion": _ai_suggestion(hit),
    }  # fmt: skip


def document(live: Live, workspace: Workspace, run_keys: dict, labels: dict, paper_keys: dict) -> dict:
    """screening.json version 2. `paper_keys` covers every member and every referenced outside paper."""
    hit_keys = _hit_keys(live)
    stage2 = {(e.paper_id, e.search_run_id): e for e in live.eligibility}
    return {
        "version": VERSION,
        "runs": [
            _run_row(run, run_keys, labels, hit_keys, paper_keys, live.cursors.get(run.id, [])) for run in live.runs
        ],
        "hits": [_hit_row(hit_keys[hit.id], hit, ref, run_keys, paper_keys, stage2) for hit, ref in live.hits],
        "eligibility": [
            {
                "paper": paper_keys[e.paper_id],
                "run": run_keys[e.search_run_id],
                "stage2_status": e.stage2_status,
                "exclude_reason": e.stage2_exclude_reason,
                "assessed_at": _iso(e.assessed_at),
            }
            for e in live.eligibility
        ],
        "links": [
            {
                "child_hit": hit_keys[link.child_hit_id],
                "parent_hit": hit_keys.get(link.parent_hit_id),
                "parent_paper": paper_keys.get(link.parent_paper_id),
                "kind": link.kind,
                "run": run_keys[link.run_id],
            }
            for link in live.links
        ],
        "branches": [
            {
                "hit": hit_keys.get(b.hit_id),
                "paper": paper_keys.get(b.paper_id),
                "state": b.state,
                "directions": b.directions or [],
                "reason": b.reason,
                "set_by": b.set_by,
            }
            for b in live.branches
        ],
        "workspace": {
            "screening_criteria": workspace.screening_criteria,
            "screening_ranked_used": workspace.screening_ranked_used,
        },
    }


# ---- import (M35c Task 2) ----
#
# The rebuild adds rows only and runs inside the import's transaction. Its runs are finished (`exhausted`, every cursor
# exhausted), so nothing fetches for them; the workspace stays read-only; no saved search is linked. The count check
# then reads the rebuilt screening back through prisma_export and compares it with the package's prisma.json.

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
    fields = SHARED_TOTALS + (RETRIEVAL_TOTALS if full_text else ())
    return all(actual[name] == expected[name] for name in fields)
