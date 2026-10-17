from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select

from app.core import discovery, enrichment, pdf_links
from app.core.discovery import Candidate
from app.core.errors import Conflict
from app.core.paper_sources import SourceSettings
from app.models import Paper, PaperStatus
from app.workers import ingest

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7\n%a found paper\n"
HOST = "https://pdf.example"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    async def resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(pdf_links, "resolve_host", resolve)


def candidate(**fields) -> Candidate:
    return Candidate(**{"title": "Found: A Paper / Part 2", "authors": ["Ada Lovelace"], "year": 2024, **fields})


async def test_the_first_url_whose_body_is_a_pdf_wins(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/landing", 200, text="<html>a landing page</html>")
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    discovery_fakes.pdf_host.reply("/later.pdf", 200, content=PDF)
    found = candidate(
        external_ids={"openalex": "W9000000003"},
        doi="10.5555/m19-found",
        venue="Proceedings of Tests",
        cited_by_count=7,
        pdf_urls=[f"{HOST}/landing", f"{HOST}/copy.pdf", f"{HOST}/later.pdf"],
    )

    paper = await discovery.add(session, discovery_fakes.providers, found, pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/landing", "/copy.pdf"]
    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert (paper.title, paper.authors, paper.year, paper.venue, paper.cited_by_count) == (
        "Found: A Paper / Part 2", ["Ada Lovelace"], 2024, "Proceedings of Tests", 7,
    )  # fmt: skip
    assert (paper.openalex_id, paper.doi, paper.manual_fields) == ("W9000000003", "10.5555/m19-found", ["title"])
    assert paper.status == PaperStatus.UPLOADED


async def test_a_paper_found_without_openalex_locks_its_doi_so_enrichment_trusts_it(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)

    by_doi = await discovery.add(
        session, discovery_fakes.providers, candidate(doi="10.5555/m19-s2", pdf_urls=[f"{HOST}/copy.pdf"]), pdf_dir
    )
    by_arxiv = await discovery.add(
        session,
        discovery_fakes.providers,
        # its own title: the same title, author and year as by_doi would be its published version (M69)
        candidate(title="Found: Another Paper", external_ids={"arxiv": "2003.07000"}, pdf_urls=[f"{HOST}/copy.pdf"]),
        pdf_dir,
    )

    assert (by_doi.doi, by_doi.openalex_id, by_doi.manual_fields) == ("10.5555/m19-s2", None, ["doi", "title"])
    assert (by_arxiv.doi, by_arxiv.manual_fields) == ("10.48550/arxiv.2003.07000", ["doi", "title"])


async def test_no_free_pdf_stores_nothing(session, discovery_fakes, pdf_dir, monkeypatch):
    monkeypatch.setattr(discovery, "MAX_PDF_BYTES", len(PDF) - 1)
    discovery_fakes.pdf_host.reply("/landing", 200, text="<html>a landing page</html>")
    discovery_fakes.pdf_host.reply("/gone.pdf", 404, text="not found")
    discovery_fakes.pdf_host.refuse("/down.pdf")
    discovery_fakes.pdf_host.reply("/huge.pdf", 200, content=PDF)
    urls = [f"{HOST}/landing", f"{HOST}/gone.pdf", f"{HOST}/down.pdf", f"{HOST}/huge.pdf"]

    with pytest.raises(Conflict, match="No free PDF was found"):
        await discovery.add(
            session, discovery_fakes.providers, candidate(doi="10.5555/m19-none", pdf_urls=urls), pdf_dir
        )

    assert len(discovery_fakes.pdf_host.requests) == 4
    assert not pdf_dir.exists() or not any(pdf_dir.iterdir())
    assert (await session.scalars(select(Paper).where(Paper.doi == "10.5555/m19-none"))).all() == []


async def test_a_candidate_with_no_urls_has_no_free_pdf(session, discovery_fakes, pdf_dir):
    with pytest.raises(Conflict, match="No free PDF was found"):
        await discovery.add(session, discovery_fakes.providers, candidate(), pdf_dir)


async def test_a_paper_already_in_the_library_is_refused_before_any_download(session, discovery_fakes, pdf_dir):
    session.add(Paper(title="Owned", file_path="/nonexistent.pdf", doi="10.5555/m19-owned"))
    await session.flush()

    with pytest.raises(Conflict, match="already in your library"):
        await discovery.add(
            session,
            discovery_fakes.providers,
            candidate(doi="10.5555/M19-Owned", pdf_urls=[f"{HOST}/copy.pdf"]),
            pdf_dir,
        )
    assert discovery_fakes.pdf_host.requests == []


async def test_a_redirect_to_the_pdf_is_followed(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/abs", 302, headers={"location": f"{HOST}/copy.pdf"})
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)

    paper = await discovery.add(session, discovery_fakes.providers, candidate(pdf_urls=[f"{HOST}/abs"]), pdf_dir)

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF


async def test_a_found_papers_title_survives_ingest_and_still_takes_a_hand_correction(
    worker_session, discovery_fakes, pdf_dir, sample_pdf, ctx
):
    """M7.5 bug: _prefill wrote candidate.title but not manual_fields, so ingest's font heuristic (sample_pdf's own
    "Deep Paper Title") overwrote it at extraction. The source's title must survive both ingest and enrichment, and
    still be replaceable by a hand correction."""
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=sample_pdf.read_bytes())
    found = candidate(title="Semantic Similarity in a Taxonomy", pdf_urls=[f"{HOST}/copy.pdf"])

    paper = await discovery.add(worker_session, discovery_fakes.providers, found, pdf_dir)
    assert "title" in paper.manual_fields

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)
    assert paper.status == "ready" and paper.title == "Semantic Similarity in a Taxonomy"

    corrected = await enrichment.correct_metadata(worker_session, paper.id, {"title": "Hand-Corrected Title"})
    assert corrected.title == "Hand-Corrected Title"


@pytest.mark.parametrize(
    ("path", "reply", "outcome"),
    [
        ("/gone.pdf", dict(status=404, text="nope"), "http_404"),
        ("/html", dict(status=200, text="<html>landing</html>"), "not_a_pdf"),
        ("/huge.pdf", dict(status=200, content=PDF), "too_large"),
        ("/cf-header", dict(status=403, headers={"cf-mitigated": "challenge"}), "bot_check"),
        (
            "/cf-page",
            dict(status=503, headers={"server": "cloudflare"}, text="<title>Just a moment...</title>"),
            "bot_check",
        ),
        ("/plain-403", dict(status=403, headers={"server": "cloudflare"}, text="forbidden"), "http_403"),
        ("/down.pdf", None, "error: ConnectError"),
    ],
)
async def test_download_pdf_says_why_each_url_failed(discovery_fakes, monkeypatch, path, reply, outcome):
    monkeypatch.setattr(discovery, "MAX_PDF_BYTES", len(PDF) - 1)
    if reply is None:
        discovery_fakes.pdf_host.refuse(path)
    else:
        status = reply.pop("status")
        discovery_fakes.pdf_host.reply(path, status, **reply)

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}{path}"])

    assert data is None and tried == [{"url": f"{HOST}{path}", "outcome": outcome}]


async def test_download_pdf_lists_the_failures_before_the_pdf_and_hides_secrets(discovery_fakes):
    discovery_fakes.pdf_host.reply("/closed", 403, text="no")
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)

    data, tried = await discovery.download_pdf(
        discovery_fakes.providers.pdf, [f"{HOST}/closed?api_key=SECRET1", f"{HOST}/copy.pdf?key=SECRET2&x=1"]
    )

    assert data == PDF
    assert tried == [
        {"url": f"{HOST}/closed?api_key=***", "outcome": "http_403"},
        {"url": f"{HOST}/copy.pdf?key=***&x=1", "outcome": "pdf"},
    ]


async def test_no_free_pdf_carries_what_was_tried_and_the_repository_copies(session, discovery_fakes, pdf_dir):
    doi = "10.5555/m63-repo"
    discovery_fakes.pdf_host.reply("/closed", 403, headers={"cf-mitigated": "challenge"})
    discovery_fakes.unpaywall.reply(
        f"/v2/{doi}",
        200,
        json={
            "best_oa_location": {"url": "https://pub.example/a", "host_type": "publisher"},
            "oa_locations": [
                {"url": "https://pub.example/a", "host_type": "publisher"},
                {"url": "https://repo.example/handle/1?api_key=SECRET", "host_type": "repository"},
                {"url": f"{HOST}/closed", "host_type": "repository"},
            ],
        },
    )

    with pytest.raises(Conflict) as caught:
        await discovery.add(
            session,
            discovery_fakes.turned_on("unpaywall"),
            candidate(doi=doi, pdf_urls=[f"{HOST}/closed?key=SECRET"]),
            pdf_dir,
        )

    assert caught.value.details == {
        "tried": [{"url": f"{HOST}/closed?key=***", "outcome": "bot_check"}],
        "free_copies": ["https://repo.example/handle/1?api_key=***", f"{HOST}/closed"],
    }


async def test_add_asks_unpaywall_once_and_tries_a_bot_checked_publisher_after_the_repository_copy(
    session, discovery_fakes, pdf_dir
):
    publisher = "https://dl.acm.org/doi/pdf/10.5555/acm"
    discovery_fakes.unpaywall.reply("/v2/10.5555/m63-acm", 200, json={
        "best_oa_location": {"url_for_pdf": publisher}, "oa_locations": [{"url_for_pdf": f"{HOST}/repo.pdf"}]
    })  # fmt: skip
    discovery_fakes.pdf_host.reply("/repo.pdf", 200, content=PDF)

    await discovery.add(
        session, discovery_fakes.turned_on("unpaywall"), candidate(doi="10.5555/m63-acm", pdf_urls=[publisher]), pdf_dir
    )

    assert [r.url.path for r in discovery_fakes.unpaywall.requests] == ["/v2/10.5555/m63-acm"]
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/repo.pdf"]


# --- M63: a landing page's declared PDF is tried once ---

PAGE = '<html><head><meta content="{url}" name="citation_pdf_url"></head></html>'


async def test_a_landing_pages_declared_pdf_is_followed_once(discovery_fakes):
    discovery_fakes.pdf_host.reply("/article", 200, text=PAGE.format(url="/article/pdf?k=SECRET&email=a@b.org"))
    discovery_fakes.pdf_host.reply("/article/pdf", 200, content=PDF)

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}/article"])

    assert data == PDF
    assert tried == [
        {"url": f"{HOST}/article", "outcome": "not_a_pdf → followed citation_pdf_url"},
        {"url": f"{HOST}/article/pdf?k=SECRET&email=***", "outcome": "pdf"},
    ]


async def test_the_followed_pdf_that_is_refused_is_recorded(discovery_fakes):
    discovery_fakes.pdf_host.reply("/article", 200, text=PAGE.format(url=f"{HOST}/article/pdf"))
    discovery_fakes.pdf_host.reply("/article/pdf", 503, text="unavailable")

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}/article"])

    assert data is None and [t["outcome"] for t in tried] == ["not_a_pdf → followed citation_pdf_url", "http_503"]


async def test_a_page_without_the_tag_makes_no_second_request(discovery_fakes):
    discovery_fakes.pdf_host.reply("/article", 200, text="<html><meta name='citation_title' content='x'></html>")

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}/article"])

    assert data is None and tried == [{"url": f"{HOST}/article", "outcome": "not_a_pdf"}]
    assert len(discovery_fakes.pdf_host.requests) == 1


async def test_a_followed_page_is_never_followed_again(discovery_fakes):
    discovery_fakes.pdf_host.reply("/a", 200, text=PAGE.format(url="/b"))
    discovery_fakes.pdf_host.reply("/b", 200, text=PAGE.format(url="/c"))

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}/a"])

    assert data is None and [t["outcome"] for t in tried] == ["not_a_pdf → followed citation_pdf_url", "not_a_pdf"]
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/a", "/b"]


async def test_a_followed_url_the_guard_refuses_is_unsafe(discovery_fakes, monkeypatch):
    async def resolve(host):
        return ["10.0.0.5"] if host == "internal.example" else ["93.184.216.34"]

    monkeypatch.setattr(pdf_links, "resolve_host", resolve)
    http = discovery_fakes.providers.pdf
    http.event_hooks["request"].append(pdf_links.guard)
    discovery_fakes.pdf_host.reply("/article", 200, text=PAGE.format(url="http://internal.example/secret.pdf"))

    data, tried = await discovery.download_pdf(http, [f"{HOST}/article"])

    assert data is None and [t["outcome"] for t in tried] == ["not_a_pdf → followed citation_pdf_url", "unsafe_url"]
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/article"]


async def test_a_declared_private_pdf_is_unsafe_on_a_client_without_the_guard(discovery_fakes, monkeypatch):
    async def resolve(host):
        return ["127.0.0.1"] if host == "localhost" else ["93.184.216.34"]

    monkeypatch.setattr(pdf_links, "resolve_host", resolve)
    discovery_fakes.pdf_host.reply("/article", 200, text=PAGE.format(url="http://127.0.0.1/x.pdf"))
    discovery_fakes.pdf_host.reply("/x.pdf", 200, content=PDF)

    data, tried = await discovery.download_pdf(discovery_fakes.providers.pdf, [f"{HOST}/article"])

    assert data is None and [t["outcome"] for t in tried] == ["not_a_pdf → followed citation_pdf_url", "unsafe_url"]
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/article"]


async def test_the_pdf_client_names_the_tool_and_never_imitates_a_browser():
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, content=PDF)

    providers = discovery.build_providers(SourceSettings(), httpx.MockTransport(handle))
    await discovery.download_pdf(providers.pdf, [f"{HOST}/a.pdf"])
    await providers.aclose()

    assert seen == ["PaperLab (+https://github.com/khannoussi-malek/PaperLab)"]


async def test_a_declared_pdf_that_redirects_to_a_private_address_is_never_requested():
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/article":
            return httpx.Response(200, text=PAGE.format(url=f"{HOST}/pdf"))
        if request.url.path == "/pdf":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/x.pdf"})
        return httpx.Response(200, content=PDF)

    providers = discovery.build_providers(SourceSettings(), httpx.MockTransport(handle))
    data, tried = await discovery.download_pdf(providers.pdf, [f"{HOST}/article"])
    await providers.aclose()

    assert data is None and tried[-1]["outcome"] == "unsafe_url"
    assert not any("127.0.0.1" in url for url in seen)


# --- M63b: a paper no source links to arXiv is looked up there by its exact title ---

REAL_TITLE = "REAL Sampling: Boosting Factuality and Diversity of Open-Ended Generation via Asymptotic Entropy"
REAL_AUTHORS = ["Haw-Shiuan Chang", "Nanyun Peng", "Mohit Bansal", "Anil Ramakrishna", "Tagyoung Chung"]
ENTRY = """<entry><id>http://arxiv.org/abs/{id}v2</id><published>{year}-06-11T00:00:00Z</published>
<title>{title}</title>{authors}</entry>"""


def atom(*entries: str) -> str:
    return '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">' + "".join(
        entries
    ) + "</feed>"  # fmt: skip


def arxiv_entry(title=REAL_TITLE, authors=REAL_AUTHORS, id="2406.07735", year=2024) -> str:
    names = "".join(f"<author><name>{name}</name></author>" for name in authors)
    return ENTRY.format(id=id, year=year, title=title, authors=names)


def tacl_like(**fields) -> Candidate:
    base = {"title": REAL_TITLE, "authors": ["Chang, Haw-Shiuan", "Peng, Nanyun"], "year": 2025}
    return candidate(**base | {"doi": "10.1162/tacl_a_00757", "pdf_urls": [f"{HOST}/closed"]} | fields)


def arxiv_world(fakes, *entries):
    fakes.pdf_host.reply("/closed", 403, headers={"cf-mitigated": "challenge"})
    fakes.arxiv.reply("/api/query", 200, text=atom(*entries))
    return fakes.turned_on("arxiv")


async def test_tacl_like_paper_found_on_arxiv_by_exact_title(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(title="Another Paper", id="2401.00001"), arxiv_entry())
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    tried = []

    paper = await discovery.add(session, providers, tacl_like(), pdf_dir, tried)

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert len(discovery_fakes.arxiv.requests) == 1
    assert discovery_fakes.arxiv.requests[0].url.params["max_results"] == "5"
    assert [t["outcome"] for t in tried] == ["bot_check", "arxiv_title_match", "pdf"]
    assert "2406.07735" in tried[1]["url"]


async def test_a_near_miss_title_is_not_accepted(session, discovery_fakes, pdf_dir):
    near = arxiv_entry(title="REAL Sampling: Boosting Factuality and Diversity of Open-Ended Generation")
    providers = arxiv_world(discovery_fakes, near)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed"]
    assert caught.value.details["tried"][-1]["outcome"] == "no_match"


async def test_an_author_mismatch_is_not_accepted(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(authors=["Someone Else"]))

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert caught.value.details["tried"][-1]["outcome"] == "no_match"
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed"]


async def test_no_authors_on_either_side_needs_the_year_within_one(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(authors=[], year=2020))
    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, tacl_like(authors=[]), pdf_dir)
    assert caught.value.details["tried"][-1]["outcome"] == "no_match"

    discovery_fakes.arxiv.reply("/api/query", 200, text=atom(arxiv_entry(authors=[], year=2024)))
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    tried = []
    await discovery.add(session, providers, tacl_like(authors=[]), pdf_dir, tried)
    assert [t["outcome"] for t in tried] == ["bot_check", "arxiv_title_match", "pdf"]


async def test_no_arxiv_search_when_a_candidate_already_has_an_arxiv_id(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry())
    discovery_fakes.pdf_host.reply("/pdf/2406.00000", 404)

    with pytest.raises(Conflict):
        await discovery.add(session, providers, tacl_like(external_ids={"arxiv": "2406.00000"}), pdf_dir)

    assert discovery_fakes.arxiv.requests == []


async def test_at_most_one_arxiv_search_per_add(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(authors=["Someone Else"]))

    with pytest.raises(Conflict):
        await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert len(discovery_fakes.arxiv.requests) == 1


async def test_no_match_is_recorded_in_tried(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert [t["outcome"] for t in caught.value.details["tried"]] == ["bot_check", "no_match"]


async def test_a_disabled_arxiv_source_is_not_searched_and_records_nothing(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/closed", 403)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.providers, tacl_like(), pdf_dir)

    assert [t["outcome"] for t in caught.value.details["tried"]] == ["http_403"]
    assert discovery_fakes.arxiv.requests == []


# --- M63b: DiVA repository records are tried as their FULLTEXT PDF ---

DIVA_RECORD = "https://kth.diva-portal.org/smash/record.jsf?pid=diva2%3A1234567&dswid=-1"
DIVA_PDF = "https://kth.diva-portal.org/smash/get/diva2:1234567/FULLTEXT01.pdf"


def repositories(fakes, doi, *urls):
    fakes.pdf_host.reply("/closed", 403, headers={"cf-mitigated": "challenge"})
    fakes.unpaywall.reply(f"/v2/{doi}", 200, json={
        "best_oa_location": None, "oa_locations": [{"url": url, "host_type": "repository"} for url in urls]
    })  # fmt: skip
    return fakes.turned_on("unpaywall")


def test_diva_record_url_becomes_fulltext_pdf():
    assert discovery.diva_pdf_url(DIVA_RECORD) == DIVA_PDF
    assert discovery.diva_pdf_url("http://uu.diva-portal.org/smash/record.jsf?pid=diva2:55") == (
        "https://uu.diva-portal.org/smash/get/diva2:55/FULLTEXT01.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://repo.example/smash/record.jsf?pid=diva2:1",
        "https://diva-portal.org.evil.example/smash/record.jsf?pid=diva2:1",
        "https://evildiva-portal.org/smash/record.jsf?pid=diva2:1",
        "https://kth.diva-portal.org/smash/record.jsf?pid=other:1",
        "https://kth.diva-portal.org/smash/get/diva2:x/FULLTEXT01.pdf",
        "not a url",
    ],
)
def test_non_diva_url_is_not_rewritten(url):
    assert discovery.diva_pdf_url(url) is None


async def test_a_diva_copy_is_tried_as_its_fulltext_pdf(session, discovery_fakes, pdf_dir):
    providers = repositories(discovery_fakes, "10.5555/diva", DIVA_RECORD, "https://repo.example/handle/1")
    discovery_fakes.pdf_host.reply("/smash/get/diva2:1234567/FULLTEXT01.pdf", 200, content=PDF)
    tried = []

    await discovery.add(session, providers, candidate(doi="10.5555/diva", pdf_urls=[f"{HOST}/closed"]), pdf_dir, tried)

    assert tried[-1] == {"url": DIVA_PDF, "outcome": "pdf"}
    assert [r.url.path for r in discovery_fakes.pdf_host.requests][-1] == "/smash/get/diva2:1234567/FULLTEXT01.pdf"


async def test_urn_kb_se_resolving_to_diva_is_tried(session, discovery_fakes, pdf_dir):
    urn = "https://urn.kb.se/resolve?urn=urn:nbn:se:kth:diva-1"
    providers = repositories(discovery_fakes, "10.5555/urn", urn)
    discovery_fakes.pdf_host.reply("/resolve", 302, headers={"location": DIVA_RECORD})
    discovery_fakes.pdf_host.reply("/smash/get/diva2:1234567/FULLTEXT01.pdf", 200, content=PDF)

    await discovery.add(session, providers, candidate(doi="10.5555/urn", pdf_urls=[f"{HOST}/closed"]), pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == [
        "/closed", "/resolve", "/smash/get/diva2:1234567/FULLTEXT01.pdf",
    ]  # fmt: skip


async def test_urn_kb_se_resolving_elsewhere_does_nothing(session, discovery_fakes, pdf_dir):
    urn = "https://urn.kb.se/resolve?urn=urn:nbn:se:x:1"
    providers = repositories(discovery_fakes, "10.5555/elsewhere", urn)
    discovery_fakes.pdf_host.reply("/resolve", 302, headers={"location": "https://repo.example/handle/1"})

    with pytest.raises(Conflict) as caught:
        found = candidate(doi="10.5555/elsewhere", pdf_urls=[f"{HOST}/closed"])
        await discovery.add(session, providers, found, pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed", "/resolve"]
    assert [t["outcome"] for t in caught.value.details["tried"]] == ["bot_check"]
    assert caught.value.details["free_copies"] == [urn]


async def test_a_diva_pdf_found_ends_the_search_with_pdf(session, discovery_fakes, pdf_dir):
    records = [f"https://kth.diva-portal.org/smash/record.jsf?pid=diva2:{n}" for n in (1, 2, 3, 4)]
    providers = repositories(discovery_fakes, "10.5555/many", *records)
    discovery_fakes.pdf_host.reply("/smash/get/diva2:1/FULLTEXT01.pdf", 404)
    discovery_fakes.pdf_host.reply("/smash/get/diva2:2/FULLTEXT01.pdf", 200, content=PDF)
    tried = []

    await discovery.add(session, providers, candidate(doi="10.5555/many", pdf_urls=[f"{HOST}/closed"]), pdf_dir, tried)

    assert [t["outcome"] for t in tried] == ["bot_check", "http_404", "pdf"]


async def test_at_most_three_diva_pdfs_are_tried(session, discovery_fakes, pdf_dir):
    records = [f"https://kth.diva-portal.org/smash/record.jsf?pid=diva2:{n}" for n in (1, 2, 3, 4)]
    providers = repositories(discovery_fakes, "10.5555/cap", *records)
    for n in (1, 2, 3, 4):
        discovery_fakes.pdf_host.reply(f"/smash/get/diva2:{n}/FULLTEXT01.pdf", 404)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, candidate(doi="10.5555/cap", pdf_urls=[f"{HOST}/closed"]), pdf_dir)

    assert len(caught.value.details["tried"]) == 4  # the closed publisher and three DiVA PDFs


# --- M63b review: busy arXiv, spacing, stricter authors ---


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """The arXiv spacing runs on a clock that stands still, and its sleeps are recorded, never waited."""
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(discovery, "_sleep", sleep)
    monkeypatch.setattr(discovery, "_now", lambda: 100.0)
    return sleeps


@pytest.mark.parametrize(
    ("status", "outcome"), [(429, "busy"), (503, "busy"), (500, "http_500"), (404, "http_404")]
)
async def test_an_arxiv_error_is_recorded_in_tried(session, discovery_fakes, pdf_dir, status, outcome):
    discovery_fakes.pdf_host.reply("/closed", 403, headers={"cf-mitigated": "challenge"})
    discovery_fakes.arxiv.reply("/api/query", status)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.turned_on("arxiv"), tacl_like(), pdf_dir)

    assert caught.value.details["tried"][-1] == {"url": "arxiv.org (title search)", "outcome": outcome}


async def test_an_arxiv_connection_error_is_recorded_in_tried(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/closed", 403)
    discovery_fakes.arxiv.refuse("/api/query")

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.turned_on("arxiv"), tacl_like(), pdf_dir)

    assert caught.value.details["tried"][-1]["outcome"] == "error: ConnectError"


async def test_arxiv_title_searches_on_one_providers_are_spaced_three_seconds(
    session, discovery_fakes, pdf_dir, fake_clock
):
    providers = arxiv_world(discovery_fakes)
    for _ in range(2):
        with pytest.raises(Conflict):
            await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert fake_clock == [discovery.ARXIV_SPACING]  # the first search did not wait; the second waited the 3 s out
    assert discovery.ARXIV_SPACING == 3


async def test_a_search_on_a_fresh_providers_does_not_wait(session, discovery_fakes, pdf_dir, fake_clock):
    with pytest.raises(Conflict):
        await discovery.add(session, arxiv_world(discovery_fakes), tacl_like(), pdf_dir)
    discovery_fakes.arxiv.reply("/api/query", 200, text=atom())
    other = replace(discovery_fakes.turned_on("arxiv"), last_search=[])  # a fresh Providers object
    with pytest.raises(Conflict):
        await discovery.add(session, other, tacl_like(), pdf_dir)

    assert fake_clock == []


CHANG_PENG_WANG = ["Chang, Haw-Shiuan", "Peng, Nanyun", "Wang, Wei"]


@pytest.mark.parametrize(
    ("ours", "theirs", "year", "accepted"),
    [
        (["Wang, Wei", "Chang, Haw-Shiuan"], ["Zed Quux", "Wei Wang"], 2024, False),  # a lone shared non-first surname
        (CHANG_PENG_WANG, ["Haw-Shiuan Chang", "Zed Quux"], 2024, True),  # the first author matches
        (["Zed Quux", *CHANG_PENG_WANG], ["Q. Else", "Nanyun Peng", "Wei Wang"], 2024, True),  # two surnames overlap
        (CHANG_PENG_WANG, ["Haw-Shiuan Chang"], 2027, False),  # the preprint cannot come 2 years after the paper
    ],
)
async def test_the_author_and_year_rule(session, discovery_fakes, pdf_dir, ours, theirs, year, accepted):
    providers = arxiv_world(discovery_fakes, arxiv_entry(authors=theirs, year=year))
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    found = tacl_like(authors=ours)

    if accepted:
        await discovery.add(session, providers, found, pdf_dir)
    else:
        with pytest.raises(Conflict):
            await discovery.add(session, providers, found, pdf_dir)


async def test_a_name_with_particles_matches_its_initialled_form(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(authors=["J. van der Berg"]))
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)

    await discovery.add(session, providers, tacl_like(authors=["Jan van der Berg"]), pdf_dir)


async def test_a_title_with_an_extra_suffix_is_a_near_miss(session, discovery_fakes, pdf_dir):
    providers = arxiv_world(discovery_fakes, arxiv_entry(title="REAL Sampling"))

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, providers, tacl_like(title="REAL Sampling 2"), pdf_dir)

    assert caught.value.details["tried"][-1]["outcome"] == "no_match"


async def test_at_most_three_urn_kb_se_links_are_resolved(session, discovery_fakes, pdf_dir):
    urns = [f"https://urn.kb.se/resolve?urn=urn:nbn:se:x:{n}" for n in range(5)]
    providers = repositories(discovery_fakes, "10.5555/urns", *urns)
    discovery_fakes.pdf_host.reply("/resolve", 302, headers={"location": "https://repo.example/x"})

    with pytest.raises(Conflict):
        await discovery.add(session, providers, candidate(doi="10.5555/urns", pdf_urls=[f"{HOST}/closed"]), pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests].count("/resolve") == 3


# --- M66: the library's arXiv copy is reused, not downloaded again ---

HELD_DOI = "10.48550/arxiv.2406.07735"


async def held_copy(session) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", title=REAL_TITLE, doi=HELD_DOI, source_type="preprint")
    session.add(paper)
    await session.commit()
    return paper


async def test_the_session_is_not_in_a_transaction_when_the_arxiv_pdf_is_downloaded(
    session, discovery_fakes, pdf_dir, monkeypatch
):
    providers = arxiv_world(discovery_fakes, arxiv_entry())
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    in_transaction = []
    real = discovery.download_pdf

    async def watching(*args, **kwargs):
        in_transaction.append(session.in_transaction())
        return await real(*args, **kwargs)

    monkeypatch.setattr(discovery, "download_pdf", watching)

    await discovery.add(session, providers, tacl_like(), pdf_dir)

    assert in_transaction == [False, False]  # the publisher link, then the arXiv copy


async def test_a_pdf_link_to_a_held_arxiv_copy_is_reused_without_any_download(session, discovery_fakes, pdf_dir):
    copy = await held_copy(session)
    link = "https://arxiv.org/pdf/2406.07735"

    with pytest.raises(Conflict) as raised:
        candidate = tacl_like(pdf_urls=[f"{HOST}/closed", link])
        await discovery.add(session, arxiv_world(discovery_fakes), candidate, pdf_dir)

    assert str(raised.value) == discovery.ALREADY_IN_LIBRARY and raised.value.details["paper_id"] == copy.id
    assert discovery_fakes.pdf_host.requests == [] and discovery_fakes.arxiv.requests == []
    await session.refresh(copy)
    assert copy.published_doi == "10.1162/tacl_a_00757"


async def test_the_in_library_entry_names_the_publisher_doi_and_no_arxiv_pdf_is_requested(
    session, discovery_fakes, pdf_dir
):
    await held_copy(session)

    with pytest.raises(Conflict) as raised:
        await discovery.add(session, arxiv_world(discovery_fakes, arxiv_entry()), tacl_like(), pdf_dir)

    assert raised.value.details["tried"][-1] == {"url": "https://doi.org/10.1162/tacl_a_00757", "outcome": "in_library"}
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed"]


# --- M66b: a paper renamed on publication finds its arXiv copy by the title before the colon ---

TACL_TITLE = (
    "REAL Sampling: Boosting Factuality and Diversity of Open-ended Generation by Extrapolating the Entropy of an "
    "Infinitely Large LM"
)


def renamed(**fields) -> Candidate:
    return tacl_like(**{"title": TACL_TITLE, "authors": REAL_AUTHORS, "year": 2025} | fields)


async def test_a_renamed_paper_reuses_the_held_arxiv_copy_as_its_published_version(
    session, discovery_fakes, pdf_dir, fake_clock
):
    copy = await held_copy(session)

    with pytest.raises(Conflict) as raised:
        await discovery.add(session, arxiv_world(discovery_fakes, arxiv_entry()), renamed(), pdf_dir)

    assert raised.value.details["paper_id"] == copy.id
    outcomes = [t["outcome"] for t in raised.value.details["tried"]]
    assert outcomes == ["bot_check", "no_match", "arxiv_title_prefix_match", "in_library"]
    await session.refresh(copy)
    assert copy.published_doi == "10.1162/tacl_a_00757"
    searches = [r.url.params["search_query"] for r in discovery_fakes.arxiv.requests]
    assert searches[1] == "ti:real AND ti:sampling AND au:chang"
    assert fake_clock == [discovery.ARXIV_SPACING]  # the second search waits its 3 s


async def test_a_renamed_paper_downloads_its_arxiv_copy(session, discovery_fakes, pdf_dir, fake_clock):
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    tried = []

    paper = await discovery.add(session, arxiv_world(discovery_fakes, arxiv_entry()), renamed(), pdf_dir, tried)

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert [t["outcome"] for t in tried] == ["bot_check", "no_match", "arxiv_title_prefix_match", "pdf"]
    assert "2406.07735" in tried[2]["url"]


@pytest.mark.parametrize(
    ("ours", "entry", "searches"),
    [
        ({"authors": REAL_AUTHORS[:2]}, {"authors": REAL_AUTHORS[:2]}, 1),  # 2 authors: the short prefix is too weak
        ({"title": "REAL: " + TACL_TITLE.split(": ")[1]}, {"title": "REAL: x"}, 1),  # one word before the colon
        ({"title": TACL_TITLE.replace(":", "")}, {}, 1),  # no colon
        ({"year": None}, {}, 1),  # no year to compare
        ({}, {"authors": [REAL_AUTHORS[1], REAL_AUTHORS[0], *REAL_AUTHORS[2:]]}, 2),  # authors out of order
        ({}, {"authors": REAL_AUTHORS[:4]}, 2),  # an author missing
        ({}, {"authors": [*REAL_AUTHORS[:4], "Zed Quux"]}, 2),  # an author differs
        ({}, {"title": "REAL Sampling Revisited: " + REAL_TITLE.split(": ")[1]}, 2),  # another prefix
        ({}, {"year": 2022}, 2),  # published more than 2 years after the preprint
        ({}, {"year": 2026}, 2),  # the preprint came after the paper
        ({"title": "GPT-4: " + TACL_TITLE.split(": ")[1]}, {"title": "GPT-4: x"}, 1),  # a hyphenated name is one word
        ({}, {"authors": ["Yu Chang", *REAL_AUTHORS[1:]]}, 2),  # same surnames, another first author
        ({"title": "REAL Sampling: Part II"}, {"title": "REAL Sampling: Part I"}, 2),  # the other part of a series
    ],
)
async def test_the_prefix_rule_rejects(session, discovery_fakes, pdf_dir, fake_clock, ours, entry, searches):
    providers = arxiv_world(discovery_fakes, arxiv_entry(**entry))

    with pytest.raises(Conflict) as raised:
        await discovery.add(session, providers, renamed(**ours), pdf_dir)

    assert raised.value.details["tried"][-1]["outcome"] == "no_match"
    assert len(discovery_fakes.arxiv.requests) == searches
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed"]


@pytest.mark.parametrize("year", [2024, 2026])  # published the year of the preprint, or two years on
async def test_the_prefix_rule_accepts_the_year_bounds(session, discovery_fakes, pdf_dir, fake_clock, year):
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)
    tried = []

    await discovery.add(session, arxiv_world(discovery_fakes, arxiv_entry()), renamed(year=year), pdf_dir, tried)

    assert tried[-2]["outcome"] == "arxiv_title_prefix_match"


async def test_an_error_on_the_prefix_search_is_recorded_after_the_first_no_match(
    session, discovery_fakes, pdf_dir, fake_clock
):
    providers = arxiv_world(discovery_fakes)
    calls = []

    def answer(request):
        calls.append(request)
        return httpx.Response(200, text=atom()) if len(calls) == 1 else httpx.Response(429)

    providers.clients["arxiv"]._transport = httpx.MockTransport(answer)

    with pytest.raises(Conflict) as raised:
        await discovery.add(session, providers, renamed(), pdf_dir)

    assert [t["outcome"] for t in raised.value.details["tried"]] == ["bot_check", "no_match", "busy"]


# --- M69: adding the arXiv copy of a paper the library holds as its published version reuses that paper ---

TACL_DOI = "10.1162/tacl_a_00757"


async def published_copy(session, title=REAL_TITLE, authors=REAL_AUTHORS, year=2025, **fields) -> Paper:
    defaults = {
        "doi": TACL_DOI, "venue": "Transactions of the Association for Computational Linguistics",
        "source_type": "journal_article",
    }  # fmt: skip
    paper = Paper(file_path="/nonexistent.pdf", title=title, authors=authors, year=year, **defaults | fields)
    session.add(paper)
    await session.commit()
    return paper


def arxiv_copy(**fields) -> Candidate:
    base = {
        "title": REAL_TITLE, "authors": REAL_AUTHORS, "year": 2024, "doi": HELD_DOI,
        "external_ids": {"arxiv": "2406.07735"}, "pdf_urls": [f"{HOST}/pdf/2406.07735"],
    }  # fmt: skip
    return candidate(**base | fields)


@pytest.mark.parametrize("held_title", [REAL_TITLE, TACL_TITLE])  # the same title, or renamed on publication
async def test_an_arxiv_copy_reuses_the_held_published_version(session, discovery_fakes, pdf_dir, held_title):
    held = await published_copy(session, title=held_title)

    with pytest.raises(Conflict) as raised:
        await discovery.add(session, discovery_fakes.providers, arxiv_copy(), pdf_dir)

    assert str(raised.value) == discovery.ALREADY_IN_LIBRARY and raised.value.details["paper_id"] == held.id
    assert raised.value.details["tried"] == [{"url": "https://arxiv.org/abs/2406.07735", "outcome": "in_library"}]
    assert discovery_fakes.pdf_host.requests == []  # nothing downloaded
    await session.refresh(held)
    assert (held.doi, held.venue, held.source_type) == (
        TACL_DOI, "Transactions of the Association for Computational Linguistics", "journal_article",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("held_fields", "why"),
    [
        ({"authors": ["Someone Else", "Another Person"]}, "other authors"),
        ({"year": 2020}, "published before the preprint"),
        ({"doi": "10.48550/arxiv.2406.99999", "source_type": "preprint"}, "the held paper is itself a preprint"),
        ({"title": "REAL Sampling: Something Else Entirely", "authors": REAL_AUTHORS[:2]}, "a 2-author renamed match"),
    ],
)
async def test_a_title_lookalike_is_not_reused(session, discovery_fakes, pdf_dir, held_fields, why):
    held = await published_copy(session, **held_fields)
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=PDF)

    paper = await discovery.add(session, discovery_fakes.providers, arxiv_copy(), pdf_dir)

    assert paper.id != held.id, why


async def test_a_publisher_candidate_is_not_matched_by_title(session, discovery_fakes, pdf_dir):
    await published_copy(session)
    discovery_fakes.pdf_host.reply("/other.pdf", 200, content=PDF)
    other = candidate(title=REAL_TITLE, authors=REAL_AUTHORS, year=2025, doi="10.5555/another-venue",
                      pdf_urls=[f"{HOST}/other.pdf"])  # fmt: skip

    paper = await discovery.add(session, discovery_fakes.providers, other, pdf_dir)

    assert paper.doi == "10.5555/another-venue"  # only an arXiv copy looks for its published version by title
