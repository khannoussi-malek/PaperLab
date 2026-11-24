"""Bringing hits into the library: import with a free copy when there is one, or the owner's own PDF."""

import uuid
from dataclasses import dataclass, field, replace

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.citations.references import _same_reference
from app.core.papers import papers
from app.core.search import discovery, retrieved_hits
from app.core.search.discovery import Providers, _add_unpaywall_links, download_pdf
from app.core.search.search_hits import _hit_out_dict
from app.core.workspaces import tags, workspaces
from app.domain.candidates import Candidate
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models import Paper
from app.models.references import ExternalRef, paper_references
from app.models.workspace_search import WorkspaceSearchHit


@dataclass(frozen=True)
class ImportResult:
    imported: int
    failed: int
    paper_ids: list[uuid.UUID] = field(default_factory=list)


async def _record_snowball_citation(session: AsyncSession, hit: WorkspaceSearchHit, ref_id: uuid.UUID) -> None:
    """Owner's choice (2026-10-04): once a snowball-discovered hit is acquired, record the hop as a citation edge
    so the existing Graph (paper_references + external_refs, graph.py) shows it — no separate "snowball graph"
    view needed. Only a paper-seeded hop (seed_paper_id set) has a library paper to link from; a hit-seeded hop's
    seed_paper_id stays unset (snowball()'s own ponytail note) so there's nothing to record yet.

    ponytail: this row can be overwritten by a later real references.fetch() for the seed paper (it deletes and
    replaces every row for that paper_id+direction) — acceptable, since that fetch's own Semantic Scholar/OpenAlex
    data would include the same edge anyway if it's still a real citation."""
    if hit.source_method not in ("snowball_backward", "snowball_forward") or hit.seed_paper_id is None:
        return
    direction = "cites" if hit.source_method == "snowball_backward" else "cited_by"
    await session.execute(
        pg_insert(paper_references)
        .values(paper_id=hit.seed_paper_id, ref_id=ref_id, direction=direction, position=0)
        .on_conflict_do_nothing()
    )


def _ref_candidate(ref: ExternalRef) -> Candidate:
    return Candidate(
        title=ref.title, authors=ref.authors, year=ref.year, venue=ref.venue, doi=ref.doi,
        external_ids=ref.external_ids, cited_by_count=ref.cited_by_count, abstract=ref.abstract,
    )


async def _library_paper_id(session: AsyncSession, ref: ExternalRef) -> uuid.UUID | None:
    """The library paper already holding this reference's DOI / OpenAlex id, if any."""
    [marked] = await discovery.mark_in_library(session, [_ref_candidate(ref)])
    return marked.paper_id


async def _ref_prefill(session: AsyncSession, ref: ExternalRef) -> dict:
    """Everything the ExternalRef knows, locked like discovery.add's (so ingest keeps the title and enrichment can
    match by DOI). A DOI/OpenAlex id the library already holds under another paper is left out: papers.doi is UNIQUE
    (only reachable from upload_hit_pdf; import_hits reuses that paper instead)."""
    candidate = _ref_candidate(ref)
    if await _library_paper_id(session, ref) is not None:
        candidate = Candidate(
            title=ref.title, authors=ref.authors, year=ref.year, venue=ref.venue, abstract=ref.abstract
        )
    return discovery.prefill(candidate)


async def _attach_free_copy(session: AsyncSession, providers: Providers, holder: Paper, ref: ExternalRef) -> bool:
    """A free copy for a paper saved without a PDF, attached to it (R12): the hit's own PDF links first, then the
    paper's. False when none is found, when its arXiv copy is the one held (that copy is the work's PDF; nothing is
    written onto it), or when a PDF arrived meanwhile (read `holder.has_pdf`). Raises NotFound if the paper is gone.
    ponytail: find_pdf's full source chain runs per PDF-less holder on every Import all; a "last tried" timestamp on
    the hit (PR 4's weekly re-check) would skip the ones tried recently."""
    candidate = discovery.candidate_of(holder)
    candidate = replace(candidate, pdf_urls=[*(ref.pdf_urls or []), *candidate.pdf_urls])
    try:
        data, _tried, _copies = await discovery.find_pdf(session, providers, candidate)
    except Conflict:
        return False
    if data is None:
        return False
    try:
        await papers.attach_pdf(session, holder.id, data, "imported")
    except Conflict:  # a PDF arrived since: nothing to enqueue
        return False
    return True


async def import_hits(
    session: AsyncSession, providers: Providers, workspace_id: uuid.UUID, hit_ids: list[uuid.UUID] | None
) -> ImportResult:
    """Best-effort bulk import (spec Task 9), mirroring discovery.add's one-candidate download-then-create flow:
    every targeted hit (hit_ids, or every not-yet-imported `relevant` hit) gets its own outcome, so one hit with no
    free PDF never stops the rest of the batch. A hit left `failed` is Manual acquisition's job (Task 11).
    `paper_ids` are the papers new or just given a PDF, for the route to enqueue ingest on — a core function has no
    Request to enqueue with itself. A hit whose ExternalRef.imported_as is already set (import_reference's own
    bookkeeping, same as ours below) is attached to that existing paper without downloading again, and its
    paper_id is left out of paper_ids so ingest isn't re-enqueued for a paper that already went through it."""
    await workspaces.require_writable(session, workspace_id)
    query = select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace_id)
    query = (
        query.where(WorkspaceSearchHit.id.in_(hit_ids))
        if hit_ids
        else query.where(WorkspaceSearchHit.stage1_status == "relevant")
    )
    hits = (await session.execute(query)).scalars().all()
    targeted = [h for h in hits if h.acquisition_status not in ("imported", "manual")]

    imported, failed, paper_ids, done = 0, 0, [], []
    for hit in hits:
        if hit.acquisition_status in ("imported", "manual"):
            # "manual" is its own provenance (spec §4.4/M30b's PRISMA export need it distinguished from an
            # automatic import) — re-running Import all must never quietly relabel it "imported" (I8).
            continue
        ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
        if ref is not None and hit.acquisition_status == "awaiting_pdf" and hit.paper_id is not None:
            # The paper it awaits, even one linked by title, which _held's identifiers can miss (C1).
            existing_id, by_identifier = hit.paper_id, False
        else:
            existing_id, by_identifier = await _held(session, ref) if ref is not None else (None, True)
        if existing_id is not None:
            # Already in the library — an earlier hit in this batch, an earlier run, the References panel, or a paper
            # holding the same DOI/OpenAlex id. Attach it instead of downloading/creating a duplicate, no re-ingest.
            try:
                await workspaces.add_paper(session, workspace_id, existing_id)
            except NotFound:  # deleted by another request since it was found (M78): this hit stays as it was
                continue
            if ref.imported_as is None and by_identifier:  # a title match never claims the shared reference (M67)
                ref.imported_as = existing_id
            # Saved without a PDF: linked so step 3 shows it, but not retrieved until its PDF arrives (R8).
            try:
                holder = await papers.get_paper(session, existing_id)
                has_pdf = holder.has_pdf
                if not has_pdf and await _attach_free_copy(session, providers, holder, ref):
                    has_pdf = True
                    paper_ids.append(existing_id)  # its PDF is new: the route enqueues ingest
                elif not has_pdf:
                    has_pdf = holder.has_pdf  # a PDF may have arrived meanwhile (attach_pdf re-read the row)
            except NotFound:  # deleted during the search for its copy (M78): this hit stays as it was
                continue
            hit.acquisition_status = "imported" if has_pdf else "awaiting_pdf"
            hit.paper_id = existing_id
            await _record_snowball_citation(session, hit, ref.id)
            imported += 1
            done.append(hit)
            continue
        if ref is not None and not ref.pdf_urls and ref.doi:
            # Unpaywall's real role (spec §6): DOI-only PDF enrichment for a candidate missing one, applied
            # post-merge — never a discovery source. import_hits only ever looked at pdf_urls as already stored;
            # try this once before giving up (I5). providers.client("unpaywall") may be None (source off) — the
            # helper already treats that as a no-op, same as discovery.add()'s own callers do.
            arxiv_only = {"arxiv": ref.external_ids["arxiv"]} if "arxiv" in ref.external_ids else {}
            [enriched] = await _add_unpaywall_links(
                providers.client("unpaywall"), [Candidate(title=ref.title, doi=ref.doi, external_ids=arxiv_only)]
            )
            if enriched.pdf_urls:
                ref.pdf_urls = enriched.pdf_urls
        data = (await download_pdf(providers.pdf, ref.pdf_urls))[0] if ref and ref.pdf_urls else None
        if data is None and ref is not None:  # M76: the PMC Open Access bucket, for a hit with a PMCID
            data = (await discovery.pmc_copy(providers, ref.external_ids, ref.doi, [], []))[0]
        if data is None:
            hit.acquisition_status = "failed"
            failed += 1
            continue
        paper = await papers.create_paper(
            session, f"{hit.normalized_title}.pdf", data, settings.pdf_dir,
            prefill=await _ref_prefill(session, ref),
        )
        await workspaces.add_paper(session, workspace_id, paper.id)
        same_paper = [ExternalRef.id == ref.id, *_same_reference(ref.external_ids, ref.doi)]
        await session.execute(update(ExternalRef).where(or_(*same_paper)).values(imported_as=paper.id))
        hit.acquisition_status = "imported"
        hit.paper_id = paper.id
        await _record_snowball_citation(session, hit, ref.id)
        imported += 1
        paper_ids.append(paper.id)
        done.append(hit)

    # A hit whose download failed but whose paper the workspace holds by another key (a title) is retrieved too, here
    # or by an add_paper above, so the counts come from where the targeted hits ended up, not from the loop.
    await retrieved_hits.link(session, workspace_id)
    await tags.apply_hit_tags(session, workspace_id, done)  # only hits imported now: a removed tag stays removed
    await session.commit()
    imported = sum(h.acquisition_status == "imported" for h in targeted)
    return ImportResult(imported, len(targeted) - imported, paper_ids)


async def _held(session: AsyncSession, ref: ExternalRef) -> tuple[uuid.UUID | None, bool]:
    """(the library paper this reference already is, whether an identifier matched it)."""
    existing_id = ref.imported_as or await _library_paper_id(session, ref)
    if existing_id is not None:
        return existing_id, True
    # Its other version may be held (M73): the arXiv copy by arXiv id (which learns this published version),
    # or the published version by title. Only when no identifier matched: an identifier match wins, and a
    # held duplicate of the other version must not learn a DOI another paper already answers to.
    held = await discovery.held_version(session, _ref_candidate(ref))
    return held if held is not None else (None, True)


async def upload_hit_pdf(
    session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID, filename: str | None, content: bytes
) -> tuple[dict, bool]:
    """Manual acquisition (spec Task 10) for a hit with no free PDF: the user supplies the file directly instead of
    `import_hits` finding one. Same ownership scoping and already-imported handling as `import_hits` above — a
    hit whose ExternalRef.imported_as is already set gets the existing paper attached, no new paper, no re-enqueue.
    Returns (hit, created) so the route only enqueues ingest when this call created a new paper or gave a held one
    its PDF.

    The %PDF-body check is the trust boundary for this user-uploaded file (spec's Global Constraint): reject
    before touching the already-imported branch too, using the same magic bytes `papers.create_paper` checks."""
    await workspaces.require_writable(session, workspace_id)
    if not content.startswith(papers.PDF_MAGIC):
        raise InvalidInput("uploaded file is not a PDF")

    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found")

    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    # By identifier only: held_version may write this DOI onto a held arXiv copy, which an upload must not do.
    by_identifier = (ref.imported_as or await _library_paper_id(session, ref)) if ref is not None else None
    # A hit awaiting its paper's PDF names that paper itself, even one linked by title, which no identifier finds (C1).
    awaited = hit.paper_id if hit.acquisition_status == "awaiting_pdf" else None
    held_id = awaited or by_identifier
    held = await session.get(Paper, held_id) if held_id is not None else None
    if held is not None and not held.has_pdf:
        # Saved without a PDF: the upload becomes its PDF, in place. The route enqueues ingest (created=True).
        # attach_pdf first: it locks the paper before any hit row is written (its pdf_arrived moves this hit when
        # it is awaiting), the order a paper-route attach takes them in, so the two can't deadlock.
        await papers.attach_pdf(session, held_id, content, "manual")
        await workspaces.add_paper(session, workspace_id, held_id)
        if ref is not None and ref.imported_as is None and by_identifier == held_id:  # as import_hits records it
            ref.imported_as = held_id
        hit.acquisition_status = "manual"
        hit.paper_id = held_id
        if ref is not None:
            await _record_snowball_citation(session, hit, ref.id)
        await tags.apply_hit_tags(session, workspace_id, [hit])
        await session.commit()
        return _hit_out_dict(hit, ref), True
    if awaited is not None and held is not None:  # its PDF arrived meanwhile, by another request
        raise Conflict("already_has_pdf")
    if ref is not None and ref.imported_as is not None:
        await workspaces.add_paper(session, workspace_id, ref.imported_as)
        hit.acquisition_status = "manual"
        hit.paper_id = ref.imported_as
        await _record_snowball_citation(session, hit, ref.id)
        await tags.apply_hit_tags(session, workspace_id, [hit])
        await session.commit()
        return _hit_out_dict(hit, ref), False

    paper = await papers.create_paper(
        session, filename or f"{hit.normalized_title}.pdf", content, settings.pdf_dir,
        prefill=await _ref_prefill(session, ref) if ref else None,
    )
    await workspaces.add_paper(session, workspace_id, paper.id)
    if ref is not None:
        same_paper = [ExternalRef.id == ref.id, *_same_reference(ref.external_ids, ref.doi)]
        await session.execute(update(ExternalRef).where(or_(*same_paper)).values(imported_as=paper.id))
    hit.acquisition_status = "manual"
    hit.paper_id = paper.id
    if ref is not None:
        await _record_snowball_citation(session, hit, ref.id)
    await tags.apply_hit_tags(session, workspace_id, [hit])
    await session.commit()
    return _hit_out_dict(hit, ref), True
