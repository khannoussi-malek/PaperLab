"""To read, the one in-library match, and the References page's data (M21, D121, D164–D166, D177)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, text

from app.core import graph, references
from app.core.errors import NotFound
from app.models import ExternalRef, Paper, Workspace, paper_references, workspace_papers

# Every test here hides the owner's rows (below), as the other references tests do: one worker for all of them.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:8]  # unique DOIs, OpenAlex IDs and workspace names per run (D37)
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)  # the test transaction freezes now(): To read times are set by hand


@pytest.fixture
async def library(session):
    """The dev database (D15) holds the owner's papers, references, note vectors and notes: hide them with a
    temp-table shadow (same trick as conftest.py's SHADOW_SEARCH_SOURCE), so every count is the test's own — not a
    DELETE, which on a 38k+ row external_refs forces a sequential scan of workspace_search_hits per deleted row to
    enforce its ON DELETE SET NULL foreign key (confirmed via EXPLAIN), and holds real locks other workers wait on
    until the rollback. workspace_papers is shadowed too, not because it needs hiding, but because a shadowed
    papers row's real FK partner must also be a shadow (a shadow copies no foreign keys, so the real
    workspace_papers_paper_id_fkey would otherwise check a new paper against the real, untouched public.papers)."""
    for table in ("paper_references", "note_embeddings", "external_refs", "notes", "papers", "workspace_papers"):
        await session.execute(text(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"))
    return session


async def add_papers(session, *titles: str, **fields) -> list[Paper]:
    added = [Paper(**{"file_path": "/nonexistent.pdf", "title": title, **fields}) for title in titles]
    session.add_all(added)
    await session.flush()
    return added


async def add_ref(session, title: str, **fields) -> ExternalRef:
    ref = ExternalRef(title=title, **fields)
    session.add(ref)
    await session.flush()
    return ref


async def link(session, ref: ExternalRef, *linked: Paper, direction: str = "cites") -> None:
    await session.execute(
        paper_references.insert(),
        [{"paper_id": paper.id, "ref_id": ref.id, "direction": direction, "position": 0} for paper in linked],
    )


async def add_workspace(session, *papers: Paper) -> uuid.UUID:
    workspace = Workspace(name=f"M21 {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    if papers:
        await session.execute(
            workspace_papers.insert(), [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers]
        )
    return workspace.id


def titles(rows) -> list[str]:
    return [row.title for row in rows]


async def queued(session, ref_id) -> datetime | None:
    return await session.scalar(select(ExternalRef.queued_at).where(ExternalRef.id == ref_id))


# --- To read (D164) ----------------------------------------------------------------------------------------------


async def test_queue_marks_a_reference_once_and_unqueue_clears_it(library):
    ref = await add_ref(library, "To read later")

    assert await references.queue(library, ref.id) is not None
    await library.execute(text("UPDATE external_refs SET queued_at = :at WHERE id = :id"), {"at": T0, "id": ref.id})
    assert await references.queue(library, ref.id) == T0  # a second To read keeps the first time

    await references.unqueue(library, ref.id)
    await references.unqueue(library, ref.id)  # and a second unmark is harmless
    assert await queued(library, ref.id) is None


async def test_an_unknown_reference_can_be_neither_queued_nor_unqueued(library):
    for call in (references.queue, references.unqueue):
        with pytest.raises(NotFound):
            await call(library, uuid.uuid4())


# --- the one in-library match (D121, D165) -----------------------------------------------------------------------


async def test_the_tab_and_the_graph_compose_the_one_match():
    assert references.IN_LIBRARY in references._LISTING.text
    assert references.IN_LIBRARY in graph._EDGES


IDENTIFIERS = ["imported_as", "openalex_id", "doi_upper_cased", "arxiv_doi"]


async def matched_reference(session, identifier: str) -> tuple[Paper, Paper, ExternalRef]:
    """Two library papers cite R and R is queued, so without a match R would be co-cited and To read; a third library
    paper is R by `identifier`. Returns (a citing paper, the library paper R is, R)."""
    citing, other = await add_papers(session, "Citing one", "Citing two")
    tag = f"{RUN}{IDENTIFIERS.index(identifier)}"
    paper_fields = {
        "imported_as": {},
        "openalex_id": {"openalex_id": f"W21{tag}"},
        "doi_upper_cased": {"doi": f"10.5555/m21-{tag}"},
        "arxiv_doi": {"doi": f"10.48550/arxiv.2609.{tag}"},
    }[identifier]
    [paper] = await add_papers(session, "The reference itself", **paper_fields)
    ref_fields = {
        "imported_as": {"imported_as": paper.id},
        "openalex_id": {"external_ids": {"openalex": f"W21{tag}"}},
        "doi_upper_cased": {"doi": f"10.5555/M21-{tag.upper()}"},
        "arxiv_doi": {"external_ids": {"arxiv": f"2609.{tag.upper()}"}},
    }[identifier]
    ref = await add_ref(session, "R", queued_at=T0, **ref_fields)
    await link(session, ref, citing, other)
    return citing, paper, ref


async def tab_matches(session, citing: Paper, paper: Paper, ref: ExternalRef) -> bool:
    [row] = (await references.listing(session, citing.id, "cites")).rows
    return row.paper_id == paper.id


async def graph_matches(session, citing: Paper, paper: Paper, ref: ExternalRef) -> bool:
    links = (await graph.library_graph(session)).links
    return any((link.source, link.target, link.kind) == (citing.id, paper.id, "cites") for link in links)


async def page_matches(session, citing: Paper, paper: Paper, ref: ExternalRef) -> bool:
    """The page (unlike the tab) never lists a matched reference at all — `_PAGE`'s own `NOT EXISTS` over the
    same `in_library` CTE drops it from every section, since it's already in the library under `paper`."""
    page = await references.library_listing(session)
    listed = {row.id for row in page.to_read + page.cited_by_several + page.citing_several}
    return ref.id not in listed


CALLERS = {"tab": tab_matches, "graph": graph_matches, "page": page_matches}


@pytest.mark.parametrize("caller", list(CALLERS))
@pytest.mark.parametrize("identifier", IDENTIFIERS)
async def test_each_caller_finds_a_reference_in_the_library_by_each_identifier(library, identifier, caller):
    citing, paper, ref = await matched_reference(library, identifier)

    assert await CALLERS[caller](library, citing, paper, ref)


@pytest.mark.parametrize("lower", ["by_openalex_id", "by_doi"])
async def test_two_library_papers_matching_one_reference_show_as_the_lower_id(library, lower):
    low, high = sorted([uuid.uuid4(), uuid.uuid4()])
    by_openalex = Paper(id=low if lower == "by_openalex_id" else high, file_path="/x.pdf", title="By OpenAlex ID",
                        openalex_id=f"W21{RUN}9")  # fmt: skip
    by_doi = Paper(id=high if lower == "by_openalex_id" else low, file_path="/x.pdf", title="By DOI",
                   doi=f"10.5555/m21-{RUN}-9")  # fmt: skip
    for paper in sorted([by_openalex, by_doi], key=lambda p: p.id, reverse=True):  # the higher id is stored first,
        library.add(paper)  # so a LIMIT 1 with no ORDER BY would most likely return it
        await library.flush()
    [citing] = await add_papers(library, "Citing")
    ref = await add_ref(
        library, "One paper, two copies", external_ids={"openalex": f"W21{RUN}9"}, doi=f"10.5555/M21-{RUN.upper()}-9"
    )
    await link(library, ref, citing)

    [row] = (await references.listing(library, citing.id, "cites")).rows

    assert row.paper_id == low


@pytest.mark.parametrize("caller", ["tab", "page"])
async def test_each_listing_returns_a_references_identifiers_from_external_ids(library, caller):
    """The tab and the page each alias arxiv_id/openalex_id/s2_id out of external_ids in their own SELECT; a wrong
    key there reads as None, which the reader's citation match (by arxiv_id) would silently miss."""
    ids = {"arxiv": f"2609.{RUN}", "openalex": f"W21{RUN}ids", "semantic_scholar": f"s2-{RUN}"}
    [citing] = await add_papers(library, "Citing")
    ref = await add_ref(library, "Not in the library", external_ids=ids, queued_at=T0)  # queued: on the page's To read
    await link(library, ref, citing)

    if caller == "tab":
        [row] = (await references.listing(library, citing.id, "cites")).rows
    else:
        [row] = (await references.library_listing(library)).to_read

    assert (row.arxiv_id, row.openalex_id, row.s2_id) == (ids["arxiv"], ids["openalex"], ids["semantic_scholar"])


# --- the References page (D166, D177)-----------------------------------------------------------------------------


async def test_cited_by_several_ranks_by_cocitation_and_leaves_a_singly_cited_reference_out(library):
    p1, p2, p3 = await add_papers(library, "P1", "P2", "P3")
    r = await add_ref(library, "R", cited_by_count=5)
    s = await add_ref(library, "S", cited_by_count=5)
    u = await add_ref(library, "U", cited_by_count=10_000)
    tied_bare = await add_ref(library, "Tied, no PDF", cited_by_count=1)
    tied_pdf = await add_ref(library, "Tied, has a PDF", cited_by_count=1, pdf_urls=["https://x/p.pdf"])
    await link(library, r, p1, p2)
    await link(library, s, p1, p2, p3)
    await link(library, u, p1)
    await link(library, tied_bare, p1, p2)
    await link(library, tied_pdf, p1, p2)

    page = await references.library_listing(library)

    # A note-similarity tie (both null here) falls to a PDF tie, then to cited_by_count, as the tab ranks (D80, RANK).
    assert [(row.title, row.cocitation) for row in page.cited_by_several] == [
        ("S", 3), ("Tied, has a PDF", 2), ("R", 2), ("Tied, no PDF", 2),
    ]  # fmt: skip
    assert "U" not in titles(page.cited_by_several)


async def test_citing_several_lists_recent_works_first_even_over_a_higher_count(library):
    p1, p2, p3 = await add_papers(library, "P1", "P2", "P3")
    w1 = await add_ref(library, "W1", year=2024, cited_by_count=5)
    w2 = await add_ref(library, "W2", year=2021, cited_by_count=900)  # far higher than W1 (Spec note 6): breaks the
    w3 = await add_ref(library, "W3", year=2025, cited_by_count=5)  # tie a wrong, D80-order implementation would hit
    w4 = await add_ref(library, "W4", year=2021, cited_by_count=5)
    c = await add_ref(library, "C", cited_by_count=5)  # cited by two papers, cites none: absent from Citing several
    await link(library, w1, p1, p2, direction="cited_by")
    await link(library, w2, p1, p2, p3, direction="cited_by")
    await link(library, w3, p1, direction="cited_by")  # cites one paper only: below COCITED_MIN
    await link(library, w4, p1, p3, direction="cited_by")
    await link(library, c, p1, p2)  # direction="cites": C is a reference the papers cite, not a work citing them

    page = await references.library_listing(library)

    # Newest first, not D80's cocitation order (W2 cites 3, W1 only 2, but 2024 still comes first); a same-year tie
    # (W2, W4, both 2021) breaks on the citing count, replaced into `cocitation` for these rows (spec §3.5).
    assert [(row.title, row.cocitation) for row in page.citing_several] == [("W1", 2), ("W2", 3), ("W4", 2)]
    assert "W3" not in titles(page.citing_several) and "C" not in titles(page.citing_several)
    # C is a reference two papers cite, not a work that cites two papers: it belongs in the other section instead.
    assert ("C", 2) in [(row.title, row.cocitation) for row in page.cited_by_several]


async def test_the_workspace_scope_counts_only_its_own_papers_and_an_unknown_one_is_refused(library):
    p1, p2, p3 = await add_papers(library, "P1", "P2", "P3")
    workspace = await add_workspace(library, p1, p3)
    r = await add_ref(library, "R", cited_by_count=5)  # cocitation 2 overall, but only P1 is in the workspace
    s = await add_ref(library, "S", cited_by_count=5)  # cocitation 3 overall, P1+P3 = 2 in the workspace
    await link(library, r, p1, p2)
    await link(library, s, p1, p2, p3)

    page = await references.library_listing(library, workspace_id=workspace)

    assert titles(page.cited_by_several) == ["S"]
    # P1 and P3 each have a stored paper_references row of their own here (their "cites" edges to R/S above), which is
    # the exact signal the coverage test next door relies on ("stored rows" -> fetched, D166): both count as fetched.
    assert (page.coverage.fetched, page.coverage.total) == (2, 2)
    with pytest.raises(NotFound):
        await references.library_listing(library, workspace_id=uuid.uuid4())


async def test_a_reference_matched_to_a_library_paper_by_doi_is_left_out_of_every_section(library):
    p1, p2 = await add_papers(library, "P1", "P2")
    doi = f"10.5555/m21-{RUN}-inlib"
    await add_papers(library, "Also the library paper", doi=doi)
    ref = await add_ref(library, "Matched by DOI", doi=doi.upper(), cited_by_count=5, queued_at=T0)
    await link(library, ref, p1, p2)  # co-cited...

    page = await references.library_listing(library)

    assert "Matched by DOI" not in titles(page.cited_by_several) and "Matched by DOI" not in titles(page.to_read)


async def test_to_read_lists_every_queued_reference_across_both_directions_newest_first(library):
    p1, p2 = await add_papers(library, "P1", "P2")
    [doomed] = await add_papers(library, "About to be deleted")
    citing_work = await add_ref(library, "A citing work", queued_at=T0 + timedelta(hours=2))
    lone_ref = await add_ref(library, "One paper cites it", queued_at=T0 + timedelta(hours=1))
    unqueued_cocited = await add_ref(library, "Co-cited, not queued")
    queued_cocited = await add_ref(library, "Co-cited and queued", queued_at=T0)
    orphaned = await add_ref(library, "Its citing paper is gone", queued_at=T0 - timedelta(hours=1))
    await link(library, citing_work, p1, direction="cited_by")
    await link(library, lone_ref, p1)
    await link(library, unqueued_cocited, p1, p2)
    await link(library, queued_cocited, p1, p2)
    await link(library, orphaned, doomed)
    await library.execute(delete(Paper).where(Paper.id == doomed.id))  # its one paper_references row cascades away

    page = await references.library_listing(library)

    assert titles(page.to_read) == [
        "A citing work", "One paper cites it", "Co-cited and queued", "Its citing paper is gone",
    ]  # fmt: skip
    assert next(r for r in page.to_read if r.title == "A citing work").cocitation == 0
    assert set(titles(page.cited_by_several)) == {"Co-cited and queued", "Co-cited, not queued"}

    workspace = await add_workspace(library, p1, p2)
    scoped = await references.library_listing(library, workspace_id=workspace)
    assert "Its citing paper is gone" not in titles(scoped.to_read)  # D166: whole library only


async def test_coverage_counts_ready_or_with_stored_rows_and_lists_the_rest_by_title(library):
    now = datetime.now(timezone.utc)
    [p1] = await add_papers(library, "P1 ready", references_state="ready")
    [p2] = await add_papers(library, "P2 failed with earlier rows", references_state="failed")
    ref = await add_ref(library, "An earlier row")
    await link(library, ref, p2)
    await add_papers(library, "P3 none", references_state="none")
    await add_papers(
        library, "P4 stale", references_state="fetching", references_requested_at=now - timedelta(minutes=11)
    )
    await add_papers(library, "P5 fetching now", references_state="fetching", references_requested_at=now)

    page = await references.library_listing(library)

    assert (page.coverage.fetched, page.coverage.total) == (2, 5)
    assert [(u.title, u.state) for u in page.coverage.unfetched] == [
        ("P3 none", "none"), ("P4 stale", "failed"), ("P5 fetching now", "fetching"),
    ]  # fmt: skip
    assert next(u for u in page.coverage.unfetched if u.title == "P4 stale").error == references.FETCH_FAILED
