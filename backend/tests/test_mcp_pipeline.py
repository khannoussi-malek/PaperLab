"""M39 F1 MCP tools: workspaces, papers and adding papers, through an in-process client against the test DB."""

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from pdf_papers import chunked_paper
from sqlalchemy import func, select

from app.core import discovery, papers, pdf_links, pipeline, workspaces
from app.core.candidates import Candidate
from app.core.errors import Conflict
from app.models import Paper, PaperStatus
from app.providers import discovery_fake, unpaywall

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]
RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)


async def test_create_then_list_workspaces_with_a_description():
    created = result(await call("create_workspace", name=f"Creativity {RUN}", description="LLMs and creativity"))
    listed = result(await call("list_workspaces"))

    assert created["name"] == f"Creativity {RUN}" and created["description"] == "LLMs and creativity"
    assert any(w["name"] == f"Creativity {RUN}" and w["paper_count"] == 0 for w in listed)


async def test_create_workspace_twice_is_a_readable_conflict():
    await call("create_workspace", name=f"Twice {RUN}")
    again = await call("create_workspace", name=f"Twice {RUN}")
    assert again.is_error and again.structured_content["error"] == "workspace_name_taken"


async def test_list_papers_shows_ingest_status(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Listed paper")
    ws = await workspaces.create(session, f"Papers {RUN}")
    await workspaces.add_paper(session, ws.id, paper.id)

    rows = result(await call("list_papers", workspace=f"Papers {RUN}"))

    assert [(r["id"], r["title"]) for r in rows] == [(str(paper.id), "Listed paper")]
    assert rows[0]["status"] == paper.status


async def test_list_papers_in_an_unknown_workspace_names_the_real_ones(session):
    await workspaces.create(session, f"Real {RUN}")
    response = await call("list_papers", workspace=f"Nope {RUN}")
    assert response.is_error and response.structured_content["error"] == "unknown_workspace"
    assert f"Real {RUN}" in response.structured_content["available"]


async def test_add_then_remove_a_paper_keeps_it_in_the_library(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Moved paper")
    ws = await workspaces.create(session, f"Move {RUN}")

    added = result(await call("add_paper_to_workspace", workspace=f"Move {RUN}", paper_id=str(paper.id)))
    removed = result(await call("remove_paper_from_workspace", workspace=f"Move {RUN}", paper_id=str(paper.id)))

    assert str(ws.id) in added["workspace_ids"]
    assert removed == {"workspace": f"Move {RUN}", "paper_id": str(paper.id), "removed": True}
    assert await workspaces.papers(session, ws.id) == []
    assert (await papers.get_paper(session, paper.id)).id == paper.id


async def test_add_an_unknown_paper_to_a_workspace_is_not_found(session):
    await workspaces.create(session, f"Ghost {RUN}")
    response = await call("add_paper_to_workspace", workspace=f"Ghost {RUN}", paper_id=str(uuid.uuid4()))
    assert response.is_error and response.structured_content["error"] == "not_found"


FREE_DOI = f"{discovery_fake.DOI_PREFIX}free"


@pytest.mark.parametrize("identifier", [FREE_DOI, f"  https://doi.org/{FREE_DOI} ", f"doi:{FREE_DOI}"])
async def test_add_paper_by_doi_queues_one_ingest(session, jobs, identifier):
    added = result(await call("add_paper", identifier=identifier))

    assert added["status"] == "queued" and added["paper_id"]
    assert jobs.jobs == [("ingest_paper", added["paper_id"])]


async def test_add_paper_by_arxiv_id_with_version(jobs):
    added = result(await call("add_paper", identifier=f"arXiv:{discovery_fake.FREE_ARXIV_ID}v2"))
    assert added["status"] == "queued"
    assert len(jobs.jobs) == 1


async def test_add_paper_already_in_library_returns_it_without_a_new_job(session, jobs):
    first = result(await call("add_paper", identifier=FREE_DOI))
    again = result(await call("add_paper", identifier=FREE_DOI))

    assert again["paper_id"] == first["paper_id"]
    assert again["status"] in ("queued", "ingested")  # `ingested` once its status is ready
    assert len(jobs.jobs) == 1


NO_ARXIV_MATCH = {"url": "arxiv.org (title search)", "outcome": "no_match"}  # the offline arXiv knows no such title


@pytest.mark.parametrize("suffix", ["landing", "closed"])
async def test_no_free_pdf_returns_the_landing_page_and_stores_nothing(session, jobs, monkeypatch, suffix):
    # The offline fake answers every DOI lookup with the free fixture, so serve the landing/closed one directly.
    doi = f"{discovery_fake.DOI_PREFIX}{suffix}"
    page = [f"{discovery_fake.PDF_HOST}/page.html"] if suffix == "landing" else []

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title=f"{suffix} fixture", doi=doi, pdf_urls=page)], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=doi))

    assert added == {
        "status": "no_free_pdf",
        "paper_id": None,
        "title": added["title"],
        "landing_url": f"https://doi.org/{discovery_fake.DOI_PREFIX}{suffix}",
        "tried": [{"url": url, "outcome": "not_a_pdf"} for url in page] + [NO_ARXIV_MATCH],
        "free_copies": [],
        "note": None,
    }
    assert jobs.jobs == []


def _closed_fixture(monkeypatch, abstract: str | None = "An abstract.") -> str:
    doi = f"{discovery_fake.DOI_PREFIX}closedsave"

    async def search(_session, _providers, _query):
        found = Candidate(title="closed save fixture", doi=doi, abstract=abstract, sources=("openalex",))
        return discovery.SearchResult([found], [])

    monkeypatch.setattr(discovery, "search", search)
    return doi


async def test_mcp_add_paper_needs_the_explicit_argument(session, jobs, monkeypatch):
    doi = _closed_fixture(monkeypatch)

    refused = result(await call("add_paper", identifier=doi))
    saved = result(await call("add_paper", identifier=doi, save_without_pdf=True))

    assert refused["status"] == "no_free_pdf" and refused["paper_id"] is None
    assert saved["status"] == "saved_without_pdf" and saved["paper_id"]
    assert saved["tried"] == [NO_ARXIV_MATCH] and saved["free_copies"] == []
    paper = await session.get(Paper, uuid.UUID(saved["paper_id"]))
    assert (paper.has_pdf, paper.details_source, paper.status) == (False, "openalex", PaperStatus.EMBEDDING)
    assert jobs.jobs == [("index_abstract", saved["paper_id"])]


async def test_mcp_add_papers_saves_without_pdf_per_item_and_skips_the_job_without_an_abstract(jobs, monkeypatch):
    doi = _closed_fixture(monkeypatch, abstract=None)

    [item] = result(await call("add_papers", identifiers=[doi], save_without_pdf=True))

    assert item["status"] == "saved_without_pdf" and item["paper_id"] and item["error"] is None
    assert jobs.jobs == []


async def test_re_adding_a_paper_saved_without_a_pdf_is_already_in_library(session, jobs, monkeypatch):
    doi = _closed_fixture(monkeypatch)
    first = result(await call("add_paper", identifier=doi, save_without_pdf=True))
    marked = Candidate(title="closed save fixture", doi=doi, paper_id=uuid.UUID(first["paper_id"]))

    async def search(_session, _providers, _query):  # the real search marks what the library holds
        return discovery.SearchResult([marked], [])

    monkeypatch.setattr(discovery, "search", search)
    again = result(await call("add_paper", identifier=doi, save_without_pdf=True))
    plain = result(await call("add_paper", identifier=doi))

    assert (again["status"], again["paper_id"]) == ("already_in_library", first["paper_id"])
    assert (plain["status"], plain["paper_id"]) == ("already_in_library", first["paper_id"])
    assert plain["note"] == pipeline.NO_COPY_NOTE
    assert len(jobs.jobs) == 1  # only the first save's index_abstract
    assert await session.scalar(select(func.count()).select_from(Paper).where(Paper.doi == doi.lower())) == 1


async def test_add_paper_on_a_pdfless_held_paper_finds_a_copy_and_upgrades_it(session, jobs, pdf_dir):
    held = await papers.create_metadata_paper(session, {"title": "Held", "doi": FREE_DOI}, "manual")

    added = result(await call("add_paper", identifier=FREE_DOI))

    assert (added["status"], added["paper_id"]) == ("queued", str(held.id))
    assert jobs.jobs == [("ingest_paper", str(held.id))] and (pdf_dir / f"{held.id}.pdf").exists()
    await session.refresh(held)
    assert held.has_pdf


async def test_add_papers_on_a_pdfless_held_paper_with_no_copy_says_so(session, jobs, pdf_dir, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}closed"
    held = await papers.create_metadata_paper(session, {"title": "Closed", "doi": doi}, "manual")

    async def search(_session, _providers, _query):  # the library marks the held paper
        return discovery.SearchResult([Candidate(title="Closed", doi=doi, paper_id=held.id)], [])

    monkeypatch.setattr(discovery, "search", search)

    [item] = result(await call("add_papers", identifiers=[doi]))

    assert (item["status"], item["paper_id"]) == ("already_in_library", str(held.id))
    assert item["note"] == pipeline.NO_COPY_NOTE
    assert jobs.jobs == [] and not (pdf_dir / f"{held.id}.pdf").exists()


async def test_add_paper_on_a_pdfless_paper_with_a_held_arxiv_copy_files_only_the_copy(session, jobs, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}arxivheld"
    bare = await papers.create_metadata_paper(session, {"title": "Bare", "doi": doi}, "manual")
    copy = Paper(title="Bare", file_path="/nonexistent.pdf", status=PaperStatus.READY)
    session.add(copy)
    await session.flush()
    await workspaces.create(session, f"Arxiv {RUN}")

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Bare", doi=doi, paper_id=bare.id)], [])

    async def find_pdf(_session, _providers, _candidate):
        raise Conflict(discovery.ALREADY_IN_LIBRARY, paper_id=copy.id, tried=[])

    monkeypatch.setattr(discovery, "search", search)
    monkeypatch.setattr(discovery, "find_pdf", find_pdf)
    added = result(await call("add_paper", identifier=doi, workspace=f"Arxiv {RUN}"))

    assert (added["status"], added["paper_id"]) == ("ingested", str(copy.id))
    members = result(await call("list_papers", workspace=f"Arxiv {RUN}"))
    assert [m["id"] for m in members] == [str(copy.id)]  # not the bare paper too
    assert jobs.jobs == []


async def test_no_free_pdf_names_the_repository_copies_over_mcp(jobs, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}landing"

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Closed", doi=doi, pdf_urls=[])], [])

    async def repository_urls(_http, _doi):
        return ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"]

    monkeypatch.setattr(discovery, "search", search)
    monkeypatch.setattr(unpaywall, "repository_urls", repository_urls)
    added = result(await call("add_paper", identifier=doi))

    pmc_bucket = {"url": "https://pmc-oa-opendata.s3.amazonaws.com/?list-type=2&prefix=PMC1.", "outcome": "http_404"}
    assert added["status"] == "no_free_pdf" and added["tried"] == [NO_ARXIV_MATCH, pmc_bucket]  # M76: its PMC link
    assert added["free_copies"] == ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"]


async def test_a_paper_saved_without_pdf_keeps_the_repository_copies(jobs, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}landing"

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Closed", doi=doi, pdf_urls=[])], [])

    async def repository_urls(_http, _doi):
        return ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"]

    monkeypatch.setattr(discovery, "search", search)
    monkeypatch.setattr(unpaywall, "repository_urls", repository_urls)
    added = result(await call("add_paper", identifier=doi, save_without_pdf=True))

    assert added["status"] == "saved_without_pdf"
    assert added["free_copies"] == ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"]


async def test_a_library_paper_search_missed_answers_already_in_library_not_an_error(session, jobs, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}raced"
    held = Paper(title="Raced", doi=doi, file_path="/nonexistent.pdf", status=PaperStatus.READY)
    session.add(held)
    await session.flush()

    async def search(_session, _providers, _query):  # marks nothing: the paper "arrived" after the search
        return discovery.SearchResult([Candidate(title="Raced", doi=doi)], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=doi))

    assert (added["status"], added["paper_id"]) == ("ingested", str(held.id))


async def test_a_link_that_is_no_pdf_says_what_it_answered(jobs):
    link = f"{discovery_fake.PDF_HOST}/page.html?api_key=SECRET"
    added = result(await call("add_paper", identifier=link))
    assert added["tried"] == [{"url": f"{discovery_fake.PDF_HOST}/page.html?api_key=***", "outcome": "not_a_pdf"}]


async def test_a_title_is_refused_with_a_hint():
    response = await call("add_paper", identifier="Attention is all you need")
    assert response.is_error and response.structured_content["error"] == "invalid_identifier"


async def test_a_title_with_a_colon_is_not_taken_for_a_link():
    response = await call("add_paper", identifier="BERT: Pre-training of deep bidirectional transformers")
    assert response.is_error and response.structured_content["error"] == "invalid_identifier"


async def test_a_pdf_link_is_downloaded_and_queued(jobs):
    added = result(await call("add_paper", identifier=f"{discovery_fake.PDF_HOST}/paper.pdf"))
    assert added["status"] == "queued" and jobs.jobs == [("ingest_paper", added["paper_id"])]


async def test_a_link_to_an_html_page_is_no_free_pdf(jobs):
    link = f"{discovery_fake.PDF_HOST}/page.html"
    added = result(await call("add_paper", identifier=link))
    assert added["status"] == "no_free_pdf" and added["landing_url"] == link and jobs.jobs == []


@pytest.mark.parametrize(
    "link",
    [
        "file:///etc/passwd",
        "ftp://example.org/a.pdf",
        "http://127.0.0.1/a.pdf",
        "http://10.0.0.1/a.pdf",
        "http://[::1]/a.pdf",
        "http://169.254.169.254/latest",
        "http://[64:ff9b::a00:1]/a.pdf",
        "http://[::127.0.0.1]/a.pdf",
        "http://[fec0::1]/a.pdf",
        "http://[::1/a.pdf",
        "http://example.org:99999/a.pdf",
    ],
)
async def test_unsafe_links_are_refused_before_any_request(link, jobs):
    response = await call("add_paper", identifier=link)
    assert response.is_error and response.structured_content["error"] == "unsafe_url"


async def test_a_host_resolving_to_a_private_address_is_refused(monkeypatch):
    async def private(host):
        return ["192.168.1.20"]

    monkeypatch.setattr(pdf_links, "resolve_host", private)
    response = await call("add_paper", identifier="https://intranet.example/a.pdf")
    assert response.is_error and response.structured_content["error"] == "unsafe_url"


async def test_a_redirect_to_a_private_address_is_refused_and_never_requested(monkeypatch, jobs):
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://10.0.0.5/secret.pdf"})

    @asynccontextmanager
    async def redirecting(_session):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handle), follow_redirects=True, event_hooks={"request": [pdf_links.guard]}
        )
        providers = discovery.Providers(pdf=client)
        try:
            yield providers
        finally:
            await providers.aclose()

    monkeypatch.setattr(discovery, "open_providers", redirecting)
    response = await call("add_paper", identifier="https://pdfs.example.org/a.pdf")

    assert response.is_error and response.structured_content["error"] == "unsafe_url"
    assert asked == ["https://pdfs.example.org/a.pdf"]
    assert jobs.jobs == []


async def test_add_paper_into_a_workspace_files_it(session, jobs):
    ws = await workspaces.create(session, f"Add into {RUN}")
    added = result(await call("add_paper", identifier=FREE_DOI, workspace=f"Add into {RUN}"))
    assert [p.id for p in await workspaces.papers(session, ws.id)] == [uuid.UUID(added["paper_id"])]


async def test_an_unknown_workspace_is_refused_before_any_download(jobs):
    response = await call("add_paper", identifier=FREE_DOI, workspace=f"Nope {RUN}")
    assert response.is_error and response.structured_content["error"] == "unknown_workspace"
    assert jobs.jobs == []


@pytest.mark.parametrize(
    "link",
    [
        "https://link.springer.com/content/pdf/10.1007/s11192-020-03690-4.pdf",
        "https://www.biorxiv.org/content/10.1101/2020.03.22.002386v3.full.pdf",
    ],
)
async def test_a_publisher_link_with_a_doi_in_its_path_is_a_link_not_a_doi(link, jobs):
    added = result(await call("add_paper", identifier=link))
    assert added["status"] == "no_free_pdf" and added["landing_url"] == link and jobs.jobs == []


async def test_a_doi_that_matches_no_search_result_is_no_matching_paper(monkeypatch):
    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Other", doi="10.1234/other")], [])

    monkeypatch.setattr(discovery, "search", search)
    response = await call("add_paper", identifier=FREE_DOI)
    assert response.is_error and response.structured_content["error"] == "no_matching_paper"


async def test_a_doi_only_another_source_answered_is_still_no_matching_paper(monkeypatch):
    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Other", doi="10.1234/other", sources=("openalex",))], [])

    monkeypatch.setattr(discovery, "search", search)
    response = await call("add_paper", identifier=FREE_DOI)
    assert response.is_error and response.structured_content["error"] == "no_matching_paper"


async def test_an_alias_doi_crossref_resolved_saves_the_paper_under_the_canonical_doi(session, jobs, monkeypatch):
    # Crossref redirects an alias (10.5465/amr.2001.4378025) to its canonical DOI (10.2307/259123).
    alias, canonical = f"{discovery_fake.DOI_PREFIX}alias", f"{discovery_fake.DOI_PREFIX}canonical"

    async def search(_session, _providers, _query):
        found = Candidate(title="Unpacking Creativity", doi=canonical, abstract="A.", sources=("openalex", "crossref"))
        return discovery.SearchResult([found], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=alias, save_without_pdf=True))

    assert added["status"] == "saved_without_pdf"
    assert (await session.get(Paper, uuid.UUID(added["paper_id"]))).doi == canonical


async def test_a_failed_paper_already_in_the_library_is_queued_again(session, jobs, monkeypatch, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path, title="Failed one")
    await papers.set_status(session, paper.id, PaperStatus.FAILED, "boom")

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Failed one", doi=FREE_DOI, paper_id=paper.id)], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=FREE_DOI))

    assert added["status"] == "queued" and jobs.jobs == [("ingest_paper", str(paper.id))]
    assert (await papers.get_paper(session, paper.id)).status == PaperStatus.UPLOADED


async def test_an_empty_workspace_name_is_refused_not_ignored(jobs):
    response = await call("add_paper", identifier=FREE_DOI, workspace="")
    assert response.is_error and response.structured_content["error"] == "unknown_workspace"
    assert jobs.jobs == []


async def test_add_papers_reports_each_item(session, jobs, monkeypatch):
    opened = []
    real = discovery.open_providers
    monkeypatch.setattr(discovery, "open_providers", lambda s: (opened.append(1), real(s))[1])
    ws = await workspaces.create(session, f"Bulk {RUN}")

    nope = f"{discovery_fake.DOI_PREFIX}nope"
    identifiers = [FREE_DOI, "Attention is all you need", f" doi:{FREE_DOI} ", nope]
    items = result(await call("add_papers", identifiers=identifiers, workspace=ws.name))

    assert [(i["identifier"], i["status"], i["error"]) for i in items] == [
        (FREE_DOI, "queued", None),
        ("Attention is all you need", None, "invalid_identifier"),
        (nope, None, "no_matching_paper"),
    ]
    assert len(opened) == 1 and jobs.jobs == [("ingest_paper", items[0]["paper_id"])]
    assert [p.id for p in await workspaces.papers(session, ws.id)] == [uuid.UUID(items[0]["paper_id"])]


async def test_add_papers_items_carry_tried_and_free_copies(jobs, monkeypatch):
    doi = f"{discovery_fake.DOI_PREFIX}landing"
    page = f"{discovery_fake.PDF_HOST}/page.html"

    async def search(_session, _providers, _query):
        return discovery.SearchResult([Candidate(title="Landing", doi=doi, pdf_urls=[page])], [])

    async def repository_urls(_http, _doi):
        return ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"]

    monkeypatch.setattr(discovery, "search", search)
    monkeypatch.setattr(unpaywall, "repository_urls", repository_urls)
    single = result(await call("add_paper", identifier=doi))
    [item] = result(await call("add_papers", identifiers=[doi]))

    assert single["tried"] and single["free_copies"]
    assert item["tried"] == single["tried"] and item["free_copies"] == single["free_copies"]
    bad = result(await call("add_papers", identifiers=["Attention is all you need"]))[0]
    assert bad["tried"] == [] and bad["free_copies"] == []


async def test_add_papers_unknown_workspace_adds_nothing(jobs):
    response = await call("add_papers", identifiers=[FREE_DOI], workspace=f"Nope {RUN}")
    assert response.is_error and response.structured_content["error"] == "unknown_workspace"
    assert jobs.jobs == []


async def test_add_papers_over_the_cap(jobs):
    response = await call("add_papers", identifiers=[f"10.1/{n}" for n in range(51)])
    assert response.is_error and response.structured_content["error"] == "too_many_identifiers"
    assert response.structured_content["max"] == 50 and jobs.jobs == []


async def test_add_papers_carries_on_after_an_unexpected_failure(session, jobs, monkeypatch):
    real = pipeline._add

    async def flaky(session, providers, kind, value, workspace_uuid, *rest):
        if kind == "arxiv":
            raise RuntimeError("provider blew up")
        return await real(session, providers, kind, value, workspace_uuid, *rest)

    monkeypatch.setattr(pipeline, "_add", flaky)
    ids = [FREE_DOI, discovery_fake.FREE_ARXIV_ID, f"{discovery_fake.DOI_PREFIX}nope"]

    items = result(await call("add_papers", identifiers=ids))

    outcomes = [(i["status"], i["error"]) for i in items]
    assert outcomes == [("queued", None), (None, "failed"), (None, "no_matching_paper")]
    assert jobs.jobs[0] == ("ingest_paper", items[0]["paper_id"])
    assert await session.get(Paper, uuid.UUID(items[0]["paper_id"])) is not None


def serve(monkeypatch, handle):
    """Every provider call goes to `handle`: the PDF client and nothing else."""

    @asynccontextmanager
    async def served(_session):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handle), follow_redirects=True, event_hooks={"request": [pdf_links.guard]}
        )
        providers = discovery.Providers(pdf=client)
        try:
            yield providers
        finally:
            await providers.aclose()

    monkeypatch.setattr(discovery, "open_providers", served)


TACL_LINK = "https://direct.mit.edu/tacl/article-pdf/doi/10.1162/tacl_a_00632/2325685/tacl_a_00632.pdf"
TACL_DOI = "10.1162/tacl_a_00632"
ARXIV_PDF = "https://arxiv.org/pdf/2301.13848"


def blocked_publisher(request: httpx.Request) -> httpx.Response:
    if request.url.host == "arxiv.org":
        return httpx.Response(200, content=b"%PDF-1.7\n%arxiv copy\n")
    return httpx.Response(403, headers={"cf-mitigated": "challenge"})


async def test_a_blocked_publisher_link_falls_back_to_the_dois_free_copy(jobs, monkeypatch):
    serve(monkeypatch, blocked_publisher)
    paper = Candidate(title="TACL paper", doi=TACL_DOI, pdf_urls=[ARXIV_PDF, TACL_LINK])

    async def search(_session, _providers, query):
        return discovery.SearchResult([paper] if query == TACL_DOI else [], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=TACL_LINK))

    assert added["status"] == "queued" and jobs.jobs == [("ingest_paper", added["paper_id"])]
    assert added["tried"] == [
        {"url": TACL_LINK, "outcome": "bot_check"},
        {"url": ARXIV_PDF, "outcome": "pdf"},
    ]


async def test_a_link_whose_doi_matches_nothing_keeps_its_own_no_free_pdf(jobs, monkeypatch):
    serve(monkeypatch, blocked_publisher)

    async def search(_session, _providers, _query):
        return discovery.SearchResult([], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=TACL_LINK))

    assert added["status"] == "no_free_pdf" and added["landing_url"] == TACL_LINK
    assert added["tried"] == [{"url": TACL_LINK, "outcome": "bot_check"}]


async def test_a_failed_link_without_a_doi_does_not_search(jobs, monkeypatch):
    serve(monkeypatch, blocked_publisher)

    async def search(*_):
        pytest.fail("searched for a link without a DOI")

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier="https://pdfs.example.org/a.pdf"))
    assert added["status"] == "no_free_pdf" and added["tried"][0]["outcome"] == "bot_check"


async def test_a_link_fallback_that_finds_every_source_busy_keeps_its_own_no_free_pdf(jobs, monkeypatch):
    serve(monkeypatch, blocked_publisher)

    async def search(*_):
        raise Conflict("search_unavailable")

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=TACL_LINK))

    assert added["status"] == "no_free_pdf" and added["landing_url"] == TACL_LINK
    assert added["tried"] == [{"url": TACL_LINK, "outcome": "bot_check"}]


async def test_a_safe_link_whose_page_declares_a_private_pdf_falls_back_to_the_doi(jobs, monkeypatch):
    page = '<html><meta name="citation_pdf_url" content="http://10.0.0.5/secret.pdf"></html>'

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "arxiv.org":
            return httpx.Response(200, content=b"%PDF-1.7\n%arxiv copy\n")
        assert request.url.host != "10.0.0.5"
        return httpx.Response(200, text=page)

    serve(monkeypatch, handle)
    paper = Candidate(title="TACL paper", doi=TACL_DOI, pdf_urls=[ARXIV_PDF])

    async def search(_session, _providers, query):
        return discovery.SearchResult([paper] if query == TACL_DOI else [], [])

    monkeypatch.setattr(discovery, "search", search)
    added = result(await call("add_paper", identifier=TACL_LINK))

    assert added["status"] == "queued" and jobs.jobs == [("ingest_paper", added["paper_id"])]
    assert [t["outcome"] for t in added["tried"]][:3] == ["not_a_pdf → followed citation_pdf_url", "unsafe_url", "pdf"]


# --- M66: a publisher DOI whose arXiv copy the library already holds ---

REAL_TACL_DOI = "10.1162/tacl_a_00757"
REAL_TACL_VENUE = "Transactions of the Association for Computational Linguistics"
REAL_TITLE = "REAL Sampling: Boosting Factuality and Diversity of Open-Ended Generation via Asymptotic Entropy"
REAL_ARXIV = "2406.07735"
ATOM = (
    '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2406.07735v2</id>'
    "<published>2024-06-11T00:00:00Z</published>"
    f"<title>{REAL_TITLE}</title><author><name>Haw-Shiuan Chang</name></author>"
    "<author><name>Nanyun Peng</name></author></entry></feed>"
)  # fmt: skip


def tacl_candidate() -> Candidate:
    return Candidate(
        title=REAL_TITLE, authors=["Chang, Haw-Shiuan", "Peng, Nanyun"], year=2025, venue=REAL_TACL_VENUE,
        doi=REAL_TACL_DOI,        external_ids={"openalex": "W4412571773"}, pdf_urls=["https://pdf.example/closed"],
    )  # fmt: skip


@pytest.fixture
def real_world(discovery_fakes, monkeypatch):
    """The TACL candidate is found but a stranger to the library (no paper_id); its PDF is bot-checked; arXiv finds the
    exact title."""
    discovery_fakes.pdf_host.reply("/closed", 403, headers={"cf-mitigated": "challenge"})
    discovery_fakes.pdf_host.reply(f"/pdf/{REAL_ARXIV}", 200, content=b"%PDF-1.7\n%real\n")
    discovery_fakes.arxiv.reply("/api/query", 200, text=ATOM)
    providers = discovery_fakes.turned_on("arxiv")

    @asynccontextmanager
    async def open_providers(_session):
        yield providers

    async def search(_session, _providers, _query):
        return discovery.SearchResult([tacl_candidate()], [])

    monkeypatch.setattr(discovery, "open_providers", open_providers)
    monkeypatch.setattr(discovery, "search", search)
    return discovery_fakes


async def library_copy(session, tmp_path, doi, **fields) -> Paper:
    paper, _, _ = await chunked_paper(session, tmp_path, title=REAL_TITLE)
    for name, value in {"doi": doi, "source_type": "preprint", **fields}.items():
        setattr(paper, name, value)
    await session.commit()
    return paper


async def with_title(session) -> list[Paper]:
    return list((await session.execute(select(Paper).where(Paper.title == REAL_TITLE))).scalars())


async def test_adding_a_publisher_doi_reuses_the_arxiv_copy_in_the_library(session, tmp_path, jobs, real_world):
    copy = await library_copy(session, tmp_path, f"10.48550/arxiv.{REAL_ARXIV}", openalex_id="W4399694541")
    ws = await workspaces.create(session, f"Reuse {RUN}")

    added = await pipeline.add_paper(session, REAL_TACL_DOI, workspace=f"Reuse {RUN}")

    await session.refresh(copy)
    assert [p.id for p in await with_title(session)] == [copy.id]
    assert added.paper_id == copy.id
    assert jobs.jobs == []
    assert [p.id for p in await workspaces.papers(session, ws.id)] == [copy.id]
    assert (copy.published_doi, copy.published_venue) == (REAL_TACL_DOI, REAL_TACL_VENUE)
    assert copy.peer_reviewed == "true"
    assert copy.doi == f"10.48550/arxiv.{REAL_ARXIV}"
    assert not any(r.url.path.startswith("/pdf/") for r in real_world.pdf_host.requests)  # nothing downloaded
    assert added.tried[-1] == {"url": f"https://doi.org/{REAL_TACL_DOI}", "outcome": "in_library"}


async def test_a_failed_arxiv_copy_is_requeued_when_the_publisher_doi_is_added(session, tmp_path, jobs, real_world):
    copy = await library_copy(session, tmp_path, f"10.48550/arxiv.{REAL_ARXIV}", status=PaperStatus.FAILED)

    added = await pipeline.add_paper(session, REAL_TACL_DOI)

    await session.refresh(copy)
    assert (added.status, added.paper_id) == ("queued", copy.id)
    assert copy.status == PaperStatus.UPLOADED and jobs.jobs == [("ingest_paper", str(copy.id))]


async def test_a_locked_published_doi_on_the_copy_is_kept(session, tmp_path, jobs, real_world):
    copy = await library_copy(
        session, tmp_path, f"10.48550/arxiv.{REAL_ARXIV}", published_doi="10.1/mine",
        manual_fields=["published_doi", "published_venue"], peer_reviewed="false",
    )  # fmt: skip

    added = await pipeline.add_paper(session, REAL_TACL_DOI)

    await session.refresh(copy)
    assert added.paper_id == copy.id and len(await with_title(session)) == 1
    assert (copy.published_doi, copy.published_venue) == ("10.1/mine", None)
    assert copy.peer_reviewed == "true"  # peer_reviewed only goes up


async def test_adding_the_arxiv_id_after_the_publisher_version_is_held_reuses_it(
    session, tmp_path, jobs, real_world, monkeypatch
):
    held = await library_copy(
        session, tmp_path, REAL_TACL_DOI, source_type="journal_article", year=2025,
        authors=["Haw-Shiuan Chang", "Nanyun Peng"], venue=REAL_TACL_VENUE,
    )  # fmt: skip
    candidate = Candidate(
        title=REAL_TITLE, authors=["Chang, Haw-Shiuan"], year=2024, doi=f"10.48550/arxiv.{REAL_ARXIV}",
        external_ids={"arxiv": REAL_ARXIV}, pdf_urls=[f"https://pdf.example/pdf/{REAL_ARXIV}"],
    )  # fmt: skip

    async def search(_session, _providers, _query):
        return discovery.SearchResult([candidate], [])

    real_world.pdf_host.reply(f"/pdf/{REAL_ARXIV}", 200, content=b"%PDF-1.7\n%real\n")
    monkeypatch.setattr(discovery, "search", search)
    added = await pipeline.add_paper(session, REAL_ARXIV)

    assert [p.id for p in await with_title(session)] == [held.id] and added.paper_id == held.id
    await session.refresh(held)
    assert (held.doi, held.venue) == (REAL_TACL_DOI, REAL_TACL_VENUE)  # the published record is not weakened
    assert jobs.jobs == [] and added.tried[-1]["outcome"] == "in_library"


async def test_a_failed_index_abstract_enqueue_leaves_the_paper_ready_not_embedding(session, jobs, monkeypatch):
    doi = _closed_fixture(monkeypatch)

    async def down(*_a, **_k):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(jobs, "enqueue_job", down)
    failed = await call("add_paper", identifier=doi, save_without_pdf=True)

    assert failed.is_error  # the call still fails, as add_paper's other enqueue failures do
    paper = await session.scalar(select(Paper).where(Paper.doi == doi.lower()))
    assert paper.status == PaperStatus.READY
