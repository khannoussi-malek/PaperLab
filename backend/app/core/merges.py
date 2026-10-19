"""The after-ingest merge (PR 3, R14–R16): paper M, uploaded with a PDF, turns out to be paper K, saved without one.
K is kept, since its id is what links, tags, notes and decisions point to: every row pointing at M moves to K, or is
dropped as a duplicate of K's own; K takes M's file, page count and status; M's row goes. One transaction, with an
audit row in paper_merges. A merge the guards refuse (R15) is only reported, with the reason, and changes nothing."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discovery, retrieved_hits
from app.core.candidates import Candidate
from app.core.enrichment import normalize_doi, short_id
from app.core.errors import NotFound
from app.core.papers import ABSTRACT_PAGE
from app.models import Paper, PaperMerge

IDENTIFIERS = ("doi", "openalex_id")  # UNIQUE on papers
FROM_MERGED = ("file_path", "page_count", "status", "status_error")  # the PDF and its ingest
KEPT_AS_IS = ("id", "details_source", "created_at", "manual_fields")
# A column's "nothing here" value when it isn't NULL: K takes M's value over these.
EMPTY = {"reading_pass": 0, "peer_reviewed": "unknown", "references_state": "none", "is_retracted": False}
ARRIVED_BY = "manual"  # M's PDF was an upload


@dataclass(frozen=True)
class MergeResult:
    status: str  # merged | reported (a dry run says what a real one would)
    reason: str | None = None  # why it was only reported, e.g. "kept_has_pdf" or "conflicting_hand_edits:year"
    moved: dict[str, int] = field(default_factory=dict)  # rows per step, the non-zero ones
    dry_run: bool = False


@dataclass(frozen=True)
class _Step:
    """The rows `where` picks (as `t`, with :m and :k) are updated by `change`, copied for K by `copy`, or else
    deleted. The same `where` counts them for a dry run, so it must already leave out what an earlier step drops."""

    label: str
    table: str
    where: str
    change: str | None = None
    copy: tuple[str, str] | None = None  # (columns, values): for a PK another table's FK points at, updated in place

    def sql(self) -> str:
        if self.copy:
            columns, values = self.copy
            return f"INSERT INTO {self.table} ({columns}) SELECT {values} FROM {self.table} t WHERE {self.where}"
        if self.change:
            return f"UPDATE {self.table} t SET {self.change} WHERE {self.where}"
        return f"DELETE FROM {self.table} t WHERE {self.where}"


def _not_on_kept(table: str, keys: list[str]) -> str:
    same = "".join(f" AND o.{key} = t.{key}" for key in keys)
    return f"NOT EXISTS (SELECT 1 FROM {table} o WHERE o.paper_id = :k{same})"


def _move(table: str, column: str = "paper_id", label: str | None = None) -> _Step:
    return _Step(label or table, table, f"t.{column} = :m", f"{column} = :k")


def _union(table: str, keys: list[str]) -> _Step:
    """M's rows K has no row like (same `keys`) move; the rest go with M's row (FK cascade)."""
    return _Step(table, table, f"t.paper_id = :m AND {_not_on_kept(table, keys)}", "paper_id = :k")


def _union_by_copy(table: str, key: str, *copied: str) -> _Step:
    """_union for a table whose (key, paper_id) another table's FK points at: K gets a copy (with `copied` too), so
    the children can move onto it, and M's row cascades away with M."""
    columns = ", ".join(["paper_id", key, *copied])
    values = ", ".join(["CAST(:k AS uuid)", *(f"t.{c}" for c in (key, *copied))])
    return _Step(table, table, f"t.paper_id = :m AND {_not_on_kept(table, [key])}", copy=(columns, values))


_OTHER_END = "CASE WHEN t.from_paper = :m THEN t.to_paper ELSE t.from_paper END"
# An M–K link would be K to K; an M–X link duplicates a K–X one (paper_links_pair is on the unordered pair).
_LINK_DROPPED = (
    f"(:k IN (t.from_paper, t.to_paper) OR EXISTS (SELECT 1 FROM paper_links o "
    f"WHERE :k IN (o.from_paper, o.to_paper) AND {_OTHER_END} IN (o.from_paper, o.to_paper)))"
)
_ON_M = ":m IN (t.from_paper, t.to_paper)"

# Every column holding a paper id (the plan's inventory; tests/test_paper_merges.py checks it against the schema).
STEPS = (
    # K's abstract chunk goes before M's chunks come: they reuse its ordinal 0 (UNIQUE paper_id, ordinal).
    _Step("chunks_dropped", "chunks", f"t.paper_id = :k AND t.page = {ABSTRACT_PAGE}"),
    _move("chunks"),
    _move("llm_outputs"),
    _union_by_copy("note_papers", "note_id"),  # before note_anchors, whose FK is (note_id, paper_id) there
    _union("note_anchors", ["note_id", "page", "bbox"]),
    _union_by_copy("workspace_papers", "workspace_id", "added_at"),  # before paper_tags, FK (workspace_id, paper_id)
    _union("paper_tags", ["tag_id"]),  # a tag belongs to one workspace, so the tag alone says "the same"
    _union("paper_authors", []),  # K's authors when it has any, else M's
    _union("paper_topics", ["source", "label"]),
    _move("datasets"),
    _move("external_refs", "imported_as"),
    _union("paper_references", ["ref_id", "direction"]),
    _Step("paper_links_dropped", "paper_links", f"{_ON_M} AND {_LINK_DROPPED}"),
    _Step(
        "paper_links",
        "paper_links",
        f"{_ON_M} AND NOT {_LINK_DROPPED}",
        "from_paper = CASE WHEN t.from_paper = :m THEN :k ELSE t.from_paper END, "
        "to_paper = CASE WHEN t.to_paper = :m THEN :k ELSE t.to_paper END",
    ),
    _move("workspace_search_hits"),
    _move("workspace_search_hits", "seed_paper_id", "workspace_search_hits_seeded"),
    _union("search_run_eligibility", ["search_run_id"]),  # K's verdict wins
    # K's card can only be the failed needs_full_text one (no PDF); a real card would collide below and roll back.
    _Step("evidence_cards_dropped", "evidence_cards", "t.paper_id = :k AND t.status = 'failed'"),
    _move("evidence_cards"),
)
_AWAITING = (
    "SELECT count(*) FROM workspace_search_hits WHERE paper_id IN (:k, :m) AND acquisition_status = 'awaiting_pdf'"
)


def _normal(column: str, value: str) -> str:
    if column == "doi":
        return normalize_doi(value) or value.strip().lower()
    return (short_id(value.strip()) or "").upper()


def _identifier(kept: Paper, identifier: tuple[str, str] | None) -> str | None:
    column, value = identifier or next(((c, getattr(kept, c)) for c in IDENTIFIERS if getattr(kept, c)), (None, None))
    return f"{column}:{_normal(column, value)}" if column else None


def _refusal(kept: Paper, merged: Paper, identifier: tuple[str, str] | None) -> str | None:
    """R15: why M must not merge into K, or None."""
    if kept.has_pdf:
        return "kept_has_pdf"
    if not merged.has_pdf:
        return "merged_has_no_pdf"
    pairs = [(c, getattr(kept, c), getattr(merged, c)) for c in IDENTIFIERS]
    if identifier:
        pairs.append((identifier[0], getattr(kept, identifier[0]), identifier[1]))
    if any(ours and theirs and _normal(c, ours) != _normal(c, theirs) for c, ours, theirs in pairs):
        return "identifier_differs"
    theirs = {"title": merged.title, "authors": merged.authors, "year": merged.year}
    if not discovery._same_work(Candidate(kept.title, kept.authors, kept.year), theirs):
        return "not_the_same_work"
    for name in sorted(set(kept.manual_fields) & set(merged.manual_fields)):
        if getattr(kept, name, None) != getattr(merged, name, None):
            return f"conflicting_hand_edits:{name}"
    return None


def _empty(name: str, value: Any) -> bool:
    return value is None or value in ("", []) or (name in EMPTY and value == EMPTY[name])


def _kept_columns(kept: Paper, merged: Paper) -> dict[str, Any]:
    """K's columns after the merge: M's PDF; K's value unless it has none; a hand edit on either side wins (the
    guards refused a clash), and K's manual_fields gain M's."""
    values = {}
    for name in Paper.__table__.columns.keys():
        ours, theirs = getattr(kept, name), getattr(merged, name)
        if name in FROM_MERGED:
            values[name] = theirs
        elif name not in KEPT_AS_IS and name not in kept.manual_fields:
            hand_edited = name in merged.manual_fields
            values[name] = theirs if hand_edited or _empty(name, ours) else ours
    values["manual_fields"] = [*kept.manual_fields, *(f for f in merged.manual_fields if f not in kept.manual_fields)]
    return values


async def _papers(session: AsyncSession, ids: tuple[uuid.UUID, uuid.UUID], lock: bool) -> dict[uuid.UUID, Paper]:
    found = {}
    for paper_id in sorted(ids):  # one lock order, so two merges of the same pair can't deadlock
        paper = await session.get(Paper, paper_id, with_for_update=True if lock else None, populate_existing=True)
        if paper is None:
            raise NotFound(f"paper {paper_id} not found")
        found[paper_id] = paper
    return found


async def merge(
    session: AsyncSession,
    merged_id: uuid.UUID,
    kept_id: uuid.UUID,
    *,
    identifier: tuple[str, str] | None = None,
    dry_run: bool = False,
) -> MergeResult:
    """Merges M (`merged_id`) into K (`kept_id`) and commits, or reports why not (R15) with a `reported` audit row.
    `identifier` is the (column, value) M learned that K holds, when a collision led here; the guards check it too.
    A dry run runs the same guards and counts per step, and writes nothing, not even the audit row. On any failure
    everything rolls back and the error propagates: both papers stay as they were. Raises NotFound."""
    if merged_id == kept_id:
        raise ValueError("a paper can't merge into itself")
    try:
        papers = await _papers(session, (merged_id, kept_id), lock=not dry_run)
        kept, merged = papers[kept_id], papers[merged_id]
        audit = {"kept_id": kept_id, "merged_id": merged_id, "identifier": _identifier(kept, identifier)}
        if reason := _refusal(kept, merged, identifier):
            if not dry_run:
                session.add(PaperMerge(**audit, status="reported", reason=reason, moved={}))
                await session.commit()
            return MergeResult("reported", reason, dry_run=dry_run)
        moved = await (_count(session, kept, merged) if dry_run else _move_rows(session, kept, merged))
        if not dry_run:
            await _absorb(session, kept, merged)
            session.add(PaperMerge(**audit, status="merged", moved=moved))
            await session.commit()
        return MergeResult("merged", moved=moved, dry_run=dry_run)
    except BaseException:
        await session.rollback()
        raise


async def _count(session: AsyncSession, kept: Paper, merged: Paper) -> dict[str, int]:
    ids = {"m": merged.id, "k": kept.id}
    counts = {}
    for step in STEPS:
        counts[step.label] = await session.scalar(text(f"SELECT count(*) FROM {step.table} t WHERE {step.where}"), ids)
    counts["awaiting_hits_retrieved"] = await session.scalar(text(_AWAITING), ids)
    return {label: n for label, n in counts.items() if n}


async def _move_rows(session: AsyncSession, kept: Paper, merged: Paper) -> dict[str, int]:
    ids = {"m": merged.id, "k": kept.id}
    counts = {}
    for step in STEPS:
        counts[step.label] = (await session.execute(text(step.sql()), ids)).rowcount
    counts["awaiting_hits_retrieved"] = await session.scalar(text(_AWAITING), ids)
    await retrieved_hits.pdf_arrived(session, kept.id, ARRIVED_BY)
    return {label: n for label, n in counts.items() if n}


async def _absorb(session: AsyncSession, kept: Paper, merged: Paper) -> None:
    """K takes its new columns and M's row goes, M's identifiers cleared first: they are UNIQUE, and K may take them.
    Not papers.delete_paper: M's file is K's now, never unlinked. ponytail: the file keeps M's uuid name; nothing
    reads the name."""
    values = _kept_columns(kept, merged)
    for name in IDENTIFIERS:
        setattr(merged, name, None)
    await session.flush()
    for name, value in values.items():
        setattr(kept, name, value)
    await session.flush()
    await session.delete(merged)
    await session.flush()
