"""The after-ingest merge (PR 3, R14–R16): paper M, uploaded with a PDF, turns out to be paper K, saved without one.
K is kept, since its id is what links, tags, notes and decisions point to: every row pointing at M moves to K, or is
dropped as a duplicate of K's own; K takes M's file, page count and status; M's row goes. One transaction, with an
audit row in paper_merges. A merge the guards refuse (R15) is only reported, with the reason, and changes nothing."""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discovery, retrieved_hits
from app.core.candidates import Candidate
from app.core.enrichment import Collision, normalize_doi, pdf_hints, short_id
from app.core.errors import NotFound
from app.core.papers import ABSTRACT_PAGE
from app.models import Paper, PaperMerge
from app.models.workspace_search import WorkspaceSearchHit

UNIQUE_IDENTIFIERS = ("doi", "openalex_id")  # UNIQUE on papers: M's are cleared before K may take them
# What proves two papers are one work (R15b). arXiv ids aren't stored apart: an arXiv DOI is a DOI.
IDENTIFIERS = (*UNIQUE_IDENTIFIERS, "pmcid")
FROM_MERGED = ("file_path", "page_count", "status", "status_error")  # the PDF and its ingest
REFERENCES = ("references_state", "references_error", "references_requested_at")  # one fetch's state, kept together
KEPT_AS_IS = ("id", "details_source", "created_at", "manual_fields", *REFERENCES)
# A column's "nothing here" value when it isn't NULL: K takes M's value over these.
EMPTY = {"reading_pass": 0, "peer_reviewed": "unknown", "is_retracted": False}
_OPENALEX_WORK = re.compile(r"W\d+")
_PMCID = re.compile(r"PMC\d+")


@dataclass(frozen=True)
class MergeResult:
    status: str  # merged | reported. A dry run says what a real one would, as far as guards and counts can tell.
    reason: str | None = None  # why it was only reported, e.g. "kept_has_pdf" or "conflicting_hand_edits:year"
    moved: dict[str, int] = field(default_factory=dict)  # rows per step, the non-zero ones
    # True: nothing was written. ponytail: a dry run can't foresee a UNIQUE collision (a non-failed K card, a K
    # numbers dataset, a row K gained meanwhile); the real merge then raises and rolls back whole.
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


def _normal(column: str, value: str | None) -> str | None:
    """The identifier as compared, or None when empty or unparseable: such a value is missing, never equal."""
    value = (value or "").strip()
    if column == "doi":
        return normalize_doi(value)
    if column == "openalex_id":
        work = (short_id(value) or "").upper()
        return work if _OPENALEX_WORK.fullmatch(work) else None
    pmcid = value.upper()
    pmcid = pmcid if pmcid.startswith("PMC") else f"PMC{pmcid}"
    return pmcid if _PMCID.fullmatch(pmcid) else None


def _pairs(kept: Paper, merged: Paper, identifier: tuple[str, str] | None) -> list[tuple[str, str | None, str | None]]:
    """(column, K's, M's) normalised, the passed identifier first: it stands for a value M learned but couldn't keep."""
    pairs = [(c, _normal(c, getattr(kept, c)), _normal(c, getattr(merged, c))) for c in IDENTIFIERS]
    if identifier:
        column, value = identifier
        pairs.insert(0, (column, _normal(column, getattr(kept, column)), _normal(column, value)))
    return pairs


def _identifier(kept: Paper, merged: Paper, identifier: tuple[str, str] | None) -> str | None:
    """For the audit: the identifier that proves the merge, else (reported) the one that led here, else K's first."""
    pairs = _pairs(kept, merged, identifier)
    proof = next(((c, ours) for c, ours, theirs in pairs if ours and ours == theirs), None)
    led = (identifier[0], _normal(*identifier) or identifier[1]) if identifier else None
    column, value = proof or led or next(((c, ours) for c, ours, _ in pairs if ours), (None, None))
    return f"{column}:{value}" if column else None


def pdf_evidence(title: str | None, metadata: dict[str, str]) -> Candidate:
    """What the PDF itself says it is (R15c): its extracted title, before enrichment, and the authors its metadata
    names. Never M's columns after enrichment: they came from the very work whose identifier collided."""
    return Candidate((title or "").strip(), pdf_hints("", metadata).authors)


def _refusal(kept: Paper, merged: Paper, identifier: tuple[str, str] | None, evidence: Candidate | None) -> str | None:
    """R15: why M must not merge into K, or None. A merge needs proof (R15b): an identifier K holds, equal to the
    passed one or to M's own; the same work by title and authors is required on top of that, never instead. With
    `evidence` (R15c) that is the PDF's own title, not M's stored one; none is no_pdf_title."""
    if kept.has_pdf:
        return "kept_has_pdf"
    if not merged.has_pdf:
        return "merged_has_no_pdf"
    pairs = _pairs(kept, merged, identifier)
    if any(ours and theirs and ours != theirs for _, ours, theirs in pairs):
        return "identifier_differs"
    if not any(ours and ours == theirs for _, ours, theirs in pairs):
        return "no_shared_identifier"
    if evidence is not None and not evidence.title.strip():
        return "no_pdf_title"
    # ponytail: a PDF seldom names its authors or year in its metadata; M's stand in, and as they may be the matched
    # work's, the PDF's title is then the only independent evidence. Page-1 author parsing would add a second.
    title = evidence.title if evidence else merged.title
    theirs = {"title": title, "authors": (evidence and evidence.authors) or merged.authors, "year": merged.year}
    if not discovery.same_work(Candidate(kept.title, kept.authors, kept.year), theirs):
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
    # M's references move in, so K's fetch state follows them unless K's own fetch finished or M never fetched.
    if kept.references_state != "ready" and merged.references_state != "none":
        values.update({name: getattr(merged, name) for name in REFERENCES})
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
    evidence: Candidate | None = None,
    how: Literal["manual", "imported"] = "manual",
    dry_run: bool = False,
) -> MergeResult:
    """Merges M (`merged_id`) into K (`kept_id`) and commits, or reports why not (R15) with a `reported` audit row.
    `identifier` is the (column, value) M learned that K holds, when a collision led here; the guards check it too.
    `evidence` is what M's PDF itself says (pdf_evidence): when given, K must be the same work as it, not as M's
    stored title. `how` M's PDF arrived (pdf_arrived's word for K's awaiting hits): "manual", an upload, or
    "imported", a found copy (see arrival).

    It commits (or, on a failure, rolls back) the caller's session, so the caller passes one with nothing pending:
    RuntimeError otherwise, before anything is read. A dry run runs the same guards and counts per step, and writes
    nothing, not even the audit row; it can't foresee a UNIQUE collision, after which a real merge rolls back. On any
    failure everything rolls back and the error propagates: both papers stay as they were. Raises NotFound."""
    if merged_id == kept_id:
        raise ValueError("a paper can't merge into itself")
    if evidence is None and not dry_run:  # R15c for every caller: never M's stored title (enrichment's copy)
        raise ValueError("a real merge needs the PDF's own evidence (R15c): pass `evidence`")
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("merge commits the session: pass one with nothing pending")
    try:
        papers = await _papers(session, (merged_id, kept_id), lock=not dry_run)
        kept, merged = papers[kept_id], papers[merged_id]
        audit = {"kept_id": kept_id, "merged_id": merged_id, "identifier": _identifier(kept, merged, identifier)}
        if reason := _refusal(kept, merged, identifier, evidence):
            if not dry_run:
                await _report(session, audit, reason)
                await session.commit()
            return MergeResult("reported", reason, dry_run=dry_run)
        moved = await (_count(session, kept, merged) if dry_run else _move_rows(session, kept, merged, how))
        if not dry_run:
            await _absorb(session, kept, merged)
            session.add(PaperMerge(**audit, status="merged", moved=moved))
            await session.commit()
        return MergeResult("merged", moved=moved, dry_run=dry_run)
    except BaseException:
        await session.rollback()
        raise


async def _report(session: AsyncSession, audit: dict[str, Any], reason: str) -> None:
    """A reported audit row, unless the pair's latest row already says just that: a re-ingest repeats nothing.
    The caller commits."""
    pair = (PaperMerge.kept_id == audit["kept_id"], PaperMerge.merged_id == audit["merged_id"])
    latest = select(PaperMerge.status, PaperMerge.reason).where(*pair).order_by(PaperMerge.created_at.desc()).limit(1)
    if tuple((await session.execute(latest)).first() or ()) != ("reported", reason):
        session.add(PaperMerge(**audit, status="reported", reason=reason, moved={}))


async def arrival(session: AsyncSession, merged_id: uuid.UUID, default: str) -> str:
    """How M's PDF arrived, for K's awaiting hits: M's own retrieved hit's word when it has one ("imported", a found
    copy; "manual", an upload for that hit), else `default`. Read before the merge moves M's hits. ponytail: M's hits
    seldom disagree; when they do, "imported" wins."""
    query = select(WorkspaceSearchHit.acquisition_status).where(
        WorkspaceSearchHit.paper_id == merged_id, WorkspaceSearchHit.acquisition_status.in_(retrieved_hits.ARRIVALS)
    )
    return await session.scalar(query.order_by(WorkspaceSearchHit.acquisition_status).limit(1)) or default


async def _kept_holder(session: AsyncSession, collisions: list[Collision]) -> tuple[Collision | None, bool]:
    """(the first collision whose holder has no PDF, or None; whether the holders are more than one paper)."""
    holders = {c.holder_id for c in collisions}
    pdfless = set(await session.scalars(select(Paper.id).where(Paper.id.in_(holders), Paper.file_path.is_(None))))
    return next((c for c in collisions if c.holder_id in pdfless), None), len(holders) > 1


async def after_ingest(
    session: AsyncSession, paper_id: uuid.UUID, collisions: list[Collision], evidence: Candidate
) -> MergeResult | None:
    """R17: ingest found `paper_id` (M) holding identifiers other papers hold (enrich_paper's `collisions`). M merges
    into the holder saved without a PDF, or a reported audit row says why not. A holder with a PDF is today's
    duplicate: None, nothing written. Two different holders, at least one without a PDF (the DOI's and the OpenAlex
    id's), are reported as holders_disagree and neither merges: M may as well be a copy of the other one. `evidence`
    is pdf_evidence for M's PDF (R15c). Commits like merge, so the session must have nothing pending."""
    first, disagree = await _kept_holder(session, collisions)
    if first is None:
        return None
    if disagree:
        audit = {"kept_id": first.holder_id, "merged_id": paper_id, "identifier": f"{first.column}:{first.value}"}
        await _report(session, audit, "holders_disagree")
        await session.commit()
        return MergeResult("reported", "holders_disagree")
    # Ingest isn't told how the PDF came, so M's own hit says; else "manual", a plain upload being the owner's own.
    how = await arrival(session, paper_id, "manual")
    identifier = (first.column, first.value)
    return await merge(session, paper_id, first.holder_id, identifier=identifier, evidence=evidence, how=how)


async def report_failure(
    session: AsyncSession, paper_id: uuid.UUID, collisions: list[Collision], error: BaseException
) -> None:
    """after_ingest raised (a race lost, a deadlock): a reported row, merge_failed:<type>, so the pair can be found
    again; M's dropped DOI no longer leads to it. Commits."""
    first, _ = await _kept_holder(session, collisions)
    if first is not None:
        audit = {"kept_id": first.holder_id, "merged_id": paper_id, "identifier": f"{first.column}:{first.value}"}
        await _report(session, audit, f"merge_failed:{type(error).__name__}")
        await session.commit()


async def _count(session: AsyncSession, kept: Paper, merged: Paper) -> dict[str, int]:
    """The rows each step would take, read only. Its ceiling: it can't tell a step that would hit a UNIQUE index."""
    ids = {"m": merged.id, "k": kept.id}
    counts = {}
    for step in STEPS:
        counts[step.label] = await session.scalar(text(f"SELECT count(*) FROM {step.table} t WHERE {step.where}"), ids)
    counts["awaiting_hits_retrieved"] = await session.scalar(text(_AWAITING), ids)
    return {label: n for label, n in counts.items() if n}


async def _move_rows(session: AsyncSession, kept: Paper, merged: Paper, how: str) -> dict[str, int]:
    ids = {"m": merged.id, "k": kept.id}
    counts = {}
    for step in STEPS:
        counts[step.label] = (await session.execute(text(step.sql()), ids)).rowcount
    counts["awaiting_hits_retrieved"] = await session.scalar(text(_AWAITING), ids)
    await retrieved_hits.pdf_arrived(session, kept.id, how)
    return {label: n for label, n in counts.items() if n}


async def _absorb(session: AsyncSession, kept: Paper, merged: Paper) -> None:
    """K takes its new columns and M's row goes, M's identifiers cleared first: they are UNIQUE, and K may take them.
    Not papers.delete_paper: M's file is K's now, never unlinked. ponytail: the file keeps M's uuid name; nothing
    reads the name."""
    values = _kept_columns(kept, merged)
    for name in UNIQUE_IDENTIFIERS:
        setattr(merged, name, None)
    await session.flush()
    for name, value in values.items():
        setattr(kept, name, value)
    await session.flush()
    await session.delete(merged)
    await session.flush()
