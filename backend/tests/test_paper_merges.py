"""PR 3 (R14–R16): a paper uploaded with a PDF (M) merges into the paper saved without one (K) that is the same work.
K is kept: every row that points at M ends up on K, or is dropped as a duplicate of K's own, in one transaction."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from test_pdf_upgrade import awaiting
from test_retrieved_hits import failed_hit, paper, workspace

from app.core import merges, notes, papers, retrieved_hits, tags, workspaces
from app.core.chunking import ChunkDraft
from app.core.errors import NotFound
from app.models import EvidenceCard, Paper, PaperMerge
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit

pytestmark = pytest.mark.anyio

TITLE = "Sleep and memory consolidation in adults"
ABSTRACT = "Sleep helps memory consolidation in adults."
AUTHORS = ["Ada Lovelace", "Alan Turing"]
DOI = "10.1234/sleep.2021"
FILE = "/pdfs/merged.pdf"

# Every column that holds a paper id (the plan's inventory). test_the_inventory_names_every_paper_id_column keeps it
# in step with the schema.
PAPER_ID_COLUMNS = [
    ("chunks", "paper_id"),
    ("llm_outputs", "paper_id"),
    ("note_anchors", "paper_id"),
    ("note_papers", "paper_id"),
    ("workspace_papers", "paper_id"),
    ("paper_tags", "paper_id"),
    ("paper_authors", "paper_id"),
    ("paper_topics", "paper_id"),
    ("datasets", "paper_id"),
    ("external_refs", "imported_as"),
    ("paper_references", "paper_id"),
    ("paper_links", "from_paper"),
    ("paper_links", "to_paper"),
    ("workspace_search_hits", "paper_id"),
    ("workspace_search_hits", "seed_paper_id"),
    ("search_run_eligibility", "paper_id"),
    ("evidence_cards", "paper_id"),
]


async def rows_of(session, paper_id) -> dict[str, int]:
    counts = {}
    for table, column in PAPER_ID_COLUMNS:
        query = text(f"SELECT count(*) FROM {table} WHERE {column} = :p")  # noqa: S608 (names from the list above)
        counts[f"{table}.{column}"] = await session.scalar(query, {"p": paper_id})
    return counts


async def kept(session, **fields) -> Paper:
    """K: saved without a PDF, ready, with its abstract chunk on ABSTRACT_PAGE."""
    prefill = {"title": TITLE, "abstract": ABSTRACT, "authors": AUTHORS, "year": 2021, "doi": DOI, **fields}
    k = await papers.create_metadata_paper(session, {"manual_fields": ["title"], **prefill}, "crossref")
    k.status = "ready"
    await session.commit()
    return k


async def merged(session, **fields) -> Paper:
    """M: a plain upload of the same work, ingested: a PDF, two chunks, ready. Its DOI was dropped (K holds it)."""
    m = Paper(**{
        "title": TITLE, "authors": AUTHORS, "year": 2021, "file_path": FILE, "page_count": 9, "status": "ready",
        "venue": "Sleep Journal", "openalex_id": "W123", **fields,
    })  # fmt: skip
    session.add(m)
    await session.flush()
    await papers.replace_chunks(session, m.id, [
        ChunkDraft(ordinal=0, page=1, bbox=[[0, 0, 1, 1]], section_title="Intro", text="Sleep matters."),
        ChunkDraft(ordinal=1, page=2, bbox=[[0, 0, 1, 1]], section_title="Method", text="We slept."),
    ])  # fmt: skip
    return m


async def sql(session, statement: str, **params):
    return await session.scalar(text(statement), params)


async def seed_both(session):
    """K with its own workspace, tag, note, decision, awaiting hit and needs-full-text card; M with a row in every
    inventoried table, some of them duplicates of K's."""
    k = await kept(session, venue="J. Sleep", reading_pass=2)
    # M's abstract loses to K's; its hand-edited venue wins, and its triage fills K's empty one
    m = await merged(session, abstract="The PDF's abstract.", manual_fields=["venue"], triage="keep", reading_pass=1)
    ws, ws2 = await workspace(session), await workspace(session, "M2")
    x, y = await paper(session, "Another paper"), await paper(session, "A third paper")
    # K's own
    await workspaces.add_paper(session, ws.id, k.id)
    await tags.tag_papers(session, ws.id, "sleep", paper_ids=[k.id])
    note_k = await notes.create_llm_note(session, k.id, "Worth citing.", "Sleep helps memory")
    hit_k = await awaiting(session, ws, k)
    session.add(SearchRunEligibility(
        paper_id=k.id, search_run_id=ws.run_id, stage2_status="include", assessed_at=datetime.now(timezone.utc),
    ))  # fmt: skip
    session.add(EvidenceCard(paper_id=k.id, status="failed", error="needs_full_text", fields={}))
    await session.execute(
        text("INSERT INTO paper_links (from_paper, to_paper, label) VALUES (:k, :y, 'K knows Y')"),
        {"k": k.id, "y": y.id},
    )
    await session.commit()
    # M's
    chunk = await sql(session, "SELECT id FROM chunks WHERE paper_id = :m AND ordinal = 0", m=m.id)
    p = {"m": m.id, "k": k.id, "x": x.id, "y": y.id, "chunk": chunk, "note_k": note_k.id}
    for statement in [
        "INSERT INTO llm_outputs (paper_id, kind, content, model, prompt_version) VALUES (:m, 'chat', 'A', 'f', 1)",
        "WITH n AS (INSERT INTO notes (body, provenance) VALUES ('From the PDF.', 'human') RETURNING id), "
        "np AS (INSERT INTO note_papers (note_id, paper_id) SELECT id, :m FROM n) "
        "INSERT INTO note_anchors (note_id, paper_id, chunk_id, page, bbox, quoted_text) "
        "SELECT id, :m, :chunk, 1, '[[0, 0, 1, 1]]', 'Sleep matters.' FROM n",
        "INSERT INTO note_papers (note_id, paper_id) VALUES (:note_k, :m)",  # a duplicate of K's
        "WITH a AS (INSERT INTO authors (display_name) VALUES ('Ada Lovelace') RETURNING id) "
        "INSERT INTO paper_authors (paper_id, author_id, position) SELECT :m, id, 0 FROM a",
        "INSERT INTO paper_topics (paper_id, source, label, score) VALUES (:m, 'openalex', 'Sleep', 0.9)",
        "INSERT INTO datasets (name, kind, paper_id) VALUES ('Table 1', 'numbers', :m)",
        "INSERT INTO external_refs (title, imported_as) VALUES ('Sleep and memory (preprint)', :m)",
        "WITH r AS (INSERT INTO external_refs (title) VALUES ('A cited work') RETURNING id) "
        "INSERT INTO paper_references (paper_id, ref_id, direction, position) SELECT :m, id, 'cites', 0 FROM r",
        "INSERT INTO paper_links (from_paper, to_paper, label) VALUES (:m, :x, 'M extends X')",
        "INSERT INTO paper_links (from_paper, to_paper, label) VALUES (:m, :k, 'the same')",  # becomes K to K
        "INSERT INTO paper_links (from_paper, to_paper, label) VALUES (:y, :m, 'Y knows M')",  # duplicates K-Y
        "INSERT INTO evidence_cards (paper_id, status, fields) VALUES (:m, 'ready', '{\"x\": 1}')",
    ]:
        await session.execute(text(statement), p)
    await workspaces.add_paper(session, ws.id, m.id)  # a duplicate of K's membership
    await workspaces.add_paper(session, ws2.id, m.id)
    await tags.tag_papers(session, ws.id, "sleep", paper_ids=[m.id])  # a duplicate of K's tag
    await tags.tag_papers(session, ws.id, "memory", paper_ids=[m.id])
    hit_m = await failed_hit(session, ws2, title=TITLE, status="manual")
    seeded = await failed_hit(session, ws2, title="A citing work", status="not_attempted")
    hit_m.paper_id, seeded.seed_paper_id = m.id, m.id
    session.add_all([
        SearchRunEligibility(paper_id=m.id, search_run_id=ws.run_id, stage2_status="exclude"),  # K's verdict wins
        SearchRunEligibility(paper_id=m.id, search_run_id=ws2.run_id, stage2_status="include"),
    ])  # fmt: skip
    await session.commit()
    return k, m, {"ws": ws, "ws2": ws2, "x": x, "y": y, "note_k": note_k, "hit_k": hit_k, "hit_m": hit_m}


MOVED = {
    "chunks_dropped": 1,  # K's abstract chunk
    "chunks": 2,
    "llm_outputs": 1,
    "note_papers": 1,
    "note_anchors": 1,
    "workspace_papers": 1,
    "paper_tags": 1,
    "paper_authors": 1,
    "paper_topics": 1,
    "datasets": 1,
    "external_refs": 1,
    "paper_references": 1,
    "paper_links_dropped": 2,  # M-K and the Y-M duplicate of K-Y
    "paper_links": 1,
    "workspace_search_hits": 1,
    "workspace_search_hits_seeded": 1,
    "search_run_eligibility": 1,
    "evidence_cards_dropped": 1,  # K's needs-full-text placeholder
    "evidence_cards": 1,
    "awaiting_hits_retrieved": 1,
}


async def audits(session, *paper_ids) -> list[PaperMerge]:
    query = select(PaperMerge).where(PaperMerge.kept_id.in_(paper_ids) | PaperMerge.merged_id.in_(paper_ids))
    return list((await session.scalars(query)).all())


async def test_the_inventory_names_every_paper_id_column(session):
    """A new table pointing at papers must be added to the merge (and here): this fails until it is."""
    foreign_keys = await session.execute(text(
        "SELECT conrelid::regclass::text, a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
        "WHERE c.contype = 'f' AND c.confrelid = 'papers'::regclass"
    ))  # fmt: skip
    # paper_tags points at workspace_papers (workspace_id, paper_id), not at papers itself
    assert sorted([*foreign_keys.all(), ("paper_tags", "paper_id")]) == sorted(PAPER_ID_COLUMNS)


async def test_a_merge_preserves_every_paper_id_row(session):
    k, m, seeded = await seed_both(session)
    assert all((await rows_of(session, m.id)).values())  # M has a row in every inventoried table

    result = await merges.merge(session, m.id, k.id)

    assert (result.status, result.reason, result.moved) == ("merged", None, MOVED)
    assert set((await rows_of(session, m.id)).values()) == {0}
    assert await session.get(Paper, m.id, populate_existing=True) is None
    k = await session.get(Paper, k.id, populate_existing=True)
    assert (k.has_pdf, k.file_path, k.page_count, k.status, k.evidence_access) == (True, FILE, 9, "ready", "full_text")
    assert (k.title, k.abstract, k.doi, k.openalex_id, k.venue) == (TITLE, ABSTRACT, DOI, "W123", "Sleep Journal")
    assert (k.details_source, k.manual_fields, k.reading_pass, k.triage) == ("crossref", ["title", "venue"], 2, "keep")
    assert k.workspace_ids == [seeded["ws"].id, seeded["ws2"].id]
    assert [(w, t) for w, _, t in await tags.tags_of_paper(session, k.id)] == [(seeded["ws"].id, ["memory", "sleep"])]
    assert len({n.id for n in await notes.list_notes_for_paper(session, k.id)}) == 2
    assert seeded["note_k"].id in {n.id for n in await notes.list_notes_for_paper(session, k.id)}
    verdicts = await session.execute(
        select(SearchRunEligibility.search_run_id, SearchRunEligibility.stage2_status)
        .where(SearchRunEligibility.paper_id == k.id).execution_options(populate_existing=True)
    )  # fmt: skip
    assert dict(verdicts.all()) == {seeded["ws"].run_id: "include", seeded["ws2"].run_id: "include"}
    links = await session.execute(
        text("SELECT from_paper, to_paper, label FROM paper_links WHERE :k IN (from_paper, to_paper)"), {"k": k.id}
    )
    assert sorted(links.all(), key=lambda r: r.label) == [
        (k.id, seeded["y"].id, "K knows Y"),
        (k.id, seeded["x"].id, "M extends X"),
    ]
    card = await session.scalar(
        select(EvidenceCard).where(EvidenceCard.paper_id == k.id).execution_options(populate_existing=True)
    )
    assert (card.status, card.fields) == ("ready", {"x": 1})
    hits = {
        h.id: h
        for h in await session.scalars(
            select(WorkspaceSearchHit)
            .where(WorkspaceSearchHit.paper_id == k.id)
            .execution_options(populate_existing=True)
        )
    }
    assert {hits[seeded["hit_k"].id].acquisition_status, hits[seeded["hit_m"].id].acquisition_status} == {"manual"}
    [audit] = await audits(session, k.id, m.id)
    assert (audit.kept_id, audit.merged_id, audit.status, audit.reason) == (k.id, m.id, "merged", None)
    assert (audit.moved, audit.identifier) == (MOVED, f"doi:{DOI}")


async def test_the_kept_papers_abstract_chunk_is_gone_after_a_merge(session):
    k, m = await kept(session), await merged(session)
    assert [c.page for c in await papers.list_chunks(session, k.id)] == [papers.ABSTRACT_PAGE]

    await merges.merge(session, m.id, k.id)

    chunks = await papers.list_chunks(session, k.id)
    assert [(c.page, c.text) for c in chunks] == [(1, "Sleep matters."), (2, "We slept.")]  # only M's full text
    k = await session.get(Paper, k.id, populate_existing=True)
    assert k.evidence_access == "full_text"


async def columns_of(session, paper_id) -> dict:
    return dict((await session.execute(text("SELECT * FROM papers WHERE id = :p"), {"p": paper_id})).one()._mapping)


async def test_a_failed_merge_leaves_both_papers_intact(session, monkeypatch):
    k, m, _ = await seed_both(session)
    ids = (k.id, m.id)  # the rollback expires k and m
    before = {pid: (await rows_of(session, pid), await columns_of(session, pid)) for pid in ids}

    async def broken(*args, **kwargs):  # after every row has moved, before K's columns and M's delete
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(retrieved_hits, "pdf_arrived", broken)
    with pytest.raises(RuntimeError, match="the disk is full"):
        await merges.merge(session, m.id, k.id)

    assert {pid: (await rows_of(session, pid), await columns_of(session, pid)) for pid in ids} == before
    assert await audits(session, *ids) == []


async def test_two_papers_with_pdfs_are_reported_not_merged(session):
    k, m = await kept(session), await merged(session)
    k.file_path = "/pdfs/kept.pdf"
    await session.commit()

    result = await merges.merge(session, m.id, k.id)

    assert (result.status, result.reason, result.moved) == ("reported", "kept_has_pdf", {})
    assert await session.get(Paper, m.id, populate_existing=True) is not None
    [audit] = await audits(session, k.id, m.id)
    assert (audit.status, audit.reason, audit.moved) == ("reported", "kept_has_pdf", {})


async def test_a_merged_paper_without_a_pdf_is_reported(session):
    k, m = await kept(session), await merged(session)
    m.file_path = None
    await session.commit()

    result = await merges.merge(session, m.id, k.id)

    assert (result.status, result.reason) == ("reported", "merged_has_no_pdf")
    assert [a.reason for a in await audits(session, k.id, m.id)] == ["merged_has_no_pdf"]


async def test_conflicting_hand_edits_are_reported(session):
    k = await kept(session, manual_fields=["title", "year"])
    m = await merged(session, year=2022, manual_fields=["year"])

    result = await merges.merge(session, m.id, k.id)

    assert (result.status, result.reason) == ("reported", "conflicting_hand_edits:year")
    assert len(await papers.list_chunks(session, m.id)) == 2  # nothing moved
    assert [a.reason for a in await audits(session, k.id, m.id)] == ["conflicting_hand_edits:year"]


async def test_a_lookalike_with_the_same_doi_typo_is_reported(session):
    """M's DOI was mistyped into K's: the identifiers agree, but M is another paper by other authors."""
    k = await kept(session)
    m = await merged(session, title="Sleep and memory consolidation in mice", authors=["Grace Hopper"])

    result = await merges.merge(session, m.id, k.id, identifier=("doi", DOI.upper()))

    assert (result.status, result.reason) == ("reported", "not_the_same_work")
    assert {p.id for p in await session.scalars(select(Paper).where(Paper.id.in_([k.id, m.id])))} == {k.id, m.id}
    [audit] = await audits(session, k.id, m.id)
    assert (audit.reason, audit.identifier) == ("not_the_same_work", f"doi:{DOI}")


async def test_a_different_identifier_is_reported(session):
    k = await kept(session, openalex_id="W123")
    m = await merged(session, openalex_id="W999")

    by_column = await merges.merge(session, m.id, k.id, dry_run=True)
    k.openalex_id = "https://openalex.org/w999"  # the same id, written another way
    await session.commit()
    by_identifier = await merges.merge(session, m.id, k.id, identifier=("doi", "10.9999/another"))

    assert by_column.reason == by_identifier.reason == "identifier_differs"


async def test_dry_run_counts_and_writes_nothing(session):
    k, m, _ = await seed_both(session)
    before = {pid: await rows_of(session, pid) for pid in (k.id, m.id)}

    result = await merges.merge(session, m.id, k.id, dry_run=True)

    assert (result.status, result.moved, result.dry_run) == ("merged", MOVED, True)
    assert {pid: await rows_of(session, pid) for pid in (k.id, m.id)} == before
    assert (await session.get(Paper, k.id, populate_existing=True)).file_path is None
    assert await audits(session, k.id, m.id) == []
    k.file_path = "/pdfs/kept.pdf"
    await session.commit()
    reported = await merges.merge(session, m.id, k.id, dry_run=True)
    assert (reported.status, reported.reason) == ("reported", "kept_has_pdf")
    assert await audits(session, k.id, m.id) == []  # a reported dry run writes no audit row either


async def test_k_awaiting_hits_become_retrieved_on_merge(session):
    k, m = await kept(session), await merged(session)
    ws = await workspace(session)
    hit = await awaiting(session, ws, k)

    result = await merges.merge(session, m.id, k.id)

    assert result.moved["awaiting_hits_retrieved"] == 1
    hit = await session.get(WorkspaceSearchHit, hit.id, populate_existing=True)
    assert (hit.acquisition_status, hit.paper_id) == ("manual", k.id)


async def test_an_unknown_paper_is_not_found(session):
    k = await kept(session)
    with pytest.raises(NotFound):
        await merges.merge(session, uuid.uuid4(), k.id)
