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
        candidate(external_ids={"arxiv": "2003.07000"}, pdf_urls=[f"{HOST}/copy.pdf"]),
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
