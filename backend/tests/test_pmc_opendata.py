"""M76: PMC Open Access dataset (NCBI's PMC Article Datasets on AWS) as a free-PDF source. Listings recorded live
on 2026-10-19: PMC4512184 (OA, has a PDF), PMC4004805 (not OA: empty), PMC4724474 (an author manuscript: text and
XML only)."""

from pathlib import Path

import httpx
import pytest

from app.core import discovery, pdf_links
from app.core.discovery import Candidate
from app.core.errors import Conflict
from app.providers import europe_pmc, pmc_opendata

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures" / "pmc_opendata"
PDF = b"%PDF-1.7\n%a PMC paper\n"
OA_PDF = "https://pmc-oa-opendata.s3.amazonaws.com/PMC4512184.1/PMC4512184.1.pdf"
EMPTY_LISTING = "https://pmc-oa-opendata.s3.amazonaws.com/?list-type=2&prefix=PMC4004805."


def listing(pmcid: str) -> str:
    return (FIXTURES / f"list-{pmcid}.xml").read_text()


@pytest.fixture(autouse=True)
def unpaced(monkeypatch):
    monkeypatch.setattr(pmc_opendata._PACER, "min_interval_seconds", 0)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    async def resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(pdf_links, "resolve_host", resolve)


def candidate(**fields) -> Candidate:
    return Candidate(**{"title": "The Brain Functional State of Music Creation", "year": 2015, **fields})


# ---- the bucket listing ----


def test_the_pdf_key_is_the_highest_version_that_matches():
    assert pmc_opendata.pdf_key(listing("PMC4512184"), "PMC4512184") == "PMC4512184.1/PMC4512184.1.pdf"
    two = listing("PMC4512184").replace("<Key>PMC4512184.1/PMC4512184.1.json</Key>", (
        "<Key>PMC4512184.2/PMC4512184.2.pdf</Key><Key>PMC4512184.10/notes.pdf</Key>"
    ))  # fmt: skip
    assert pmc_opendata.pdf_key(two, "PMC4512184") == "PMC4512184.2/PMC4512184.2.pdf"


def test_no_pdf_for_a_closed_paper_or_an_author_manuscript():
    assert pmc_opendata.pdf_key(listing("PMC4004805"), "PMC4004805") is None
    assert pmc_opendata.pdf_key(listing("PMC4724474"), "PMC4724474") is None  # json, txt and xml only


def test_a_pmcid_is_written_with_its_prefix():
    assert pmc_opendata.normalize("4512184") == pmc_opendata.normalize("pmc4512184") == "PMC4512184"
    assert pmc_opendata.normalize("PMC 12") is None and pmc_opendata.normalize("") is None


async def test_the_listing_asks_for_one_pmcid_and_names_paperlab():
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=listing("PMC4512184"))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(answer), headers={"User-Agent": discovery.PDF_USER_AGENT}
    ) as http:
        assert await pmc_opendata.pdf_url(http, "PMC4512184") == (OA_PDF, pmc_opendata.listing_url("PMC4512184"))
    [request] = seen
    assert (request.url.host, dict(request.url.params)) == (
        "pmc-oa-opendata.s3.amazonaws.com", {"list-type": "2", "prefix": "PMC4512184."},
    )  # fmt: skip
    assert "PaperLab" in request.headers["user-agent"] and "@" not in str(request.url)


# ---- discovery.add ----


async def test_a_paper_with_a_pmcid_gets_its_pdf_from_the_bucket(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/closed", 403)
    discovery_fakes.pdf_host.reply("/", 200, text=listing("PMC4512184"))
    discovery_fakes.pdf_host.reply("/PMC4512184.1/PMC4512184.1.pdf", 200, content=PDF)
    tried = []
    found = candidate(
        doi="10.1038/srep12277", pdf_urls=["https://pdf.example/closed"], external_ids={"pmcid": "4512184"}
    )

    paper = await discovery.add(session, discovery_fakes.providers, found, pdf_dir, tried)

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert tried[-1] == {"url": OA_PDF, "outcome": "pdf"}


async def test_a_pmcid_not_in_the_bucket_is_recorded_as_no_match(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/", 200, text=listing("PMC4004805"))

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.providers, candidate(external_ids={"pmcid": "4004805"}), pdf_dir)

    assert caught.value.details["tried"][-1] == {"url": EMPTY_LISTING, "outcome": "no_match"}


async def test_a_body_that_isnt_a_pdf_is_refused(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/", 200, text=listing("PMC4512184"))
    discovery_fakes.pdf_host.reply("/PMC4512184.1/PMC4512184.1.pdf", 200, text="<html>nope</html>")

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.providers, candidate(external_ids={"pmcid": "4512184"}), pdf_dir)

    assert caught.value.details["tried"][-1] == {"url": OA_PDF, "outcome": "not_a_pdf"}


async def test_a_listing_that_fails_is_recorded_and_ends_quietly(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/", 503)

    with pytest.raises(Conflict) as caught:
        await discovery.add(session, discovery_fakes.providers, candidate(external_ids={"pmcid": "4512184"}), pdf_dir)

    assert caught.value.details["tried"][-1] == {"url": pmc_opendata.listing_url("PMC4512184"), "outcome": "http_503"}


async def test_the_pmcid_can_come_from_a_pmc_link_among_the_free_copies(session, discovery_fakes, pdf_dir):
    discovery_fakes.unpaywall.reply("/v2/10.1038/srep12277", 200, json={"best_oa_location": None, "oa_locations": [
        {"url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4512184/", "host_type": "repository"},
    ]})  # fmt: skip
    discovery_fakes.pdf_host.reply("/", 200, text=listing("PMC4512184"))
    discovery_fakes.pdf_host.reply("/PMC4512184.1/PMC4512184.1.pdf", 200, content=PDF)
    providers = discovery_fakes.turned_on("unpaywall")

    paper = await discovery.add(session, providers, candidate(doi="10.1038/srep12277"), pdf_dir)

    assert paper.doi == "10.1038/srep12277"


def test_pmc_links_are_read_in_their_usual_forms():
    assert discovery.pmcid_of({}, ["https://pmc.ncbi.nlm.nih.gov/articles/PMC4512184/"]) == "PMC4512184"
    assert discovery.pmcid_of({}, ["https://europepmc.org/articles/pmc4512184"]) == "PMC4512184"
    assert discovery.pmcid_of({}, ["https://europepmc.org/article/PMC/PMC4512184"]) == "PMC4512184"
    assert discovery.pmcid_of({"pmcid": "1"}, ["https://europepmc.org/articles/PMC2"]) == "PMC1"  # its own id first
    assert discovery.pmcid_of({}, ["https://repo.example/PMC4512184"]) is None


async def test_the_pmcid_can_come_from_europe_pmc_by_doi_when_it_is_on(session, discovery_fakes, pdf_dir):
    epmc = []

    def answer(request: httpx.Request) -> httpx.Response:
        epmc.append(request)
        return httpx.Response(200, json={"resultList": {"result": [
            {"pmcid": "PMC4512184", "doi": "10.1038/srep12277", "title": "x"},
        ]}})  # fmt: skip

    discovery_fakes.pdf_host.reply("/", 200, text=listing("PMC4512184"))
    discovery_fakes.pdf_host.reply("/PMC4512184.1/PMC4512184.1.pdf", 200, content=PDF)
    client = europe_pmc.new_client(transport=httpx.MockTransport(answer))
    on = discovery.Providers(pdf=discovery_fakes.providers.pdf, clients={**discovery_fakes.providers.clients,
                                                                        "europe_pmc": client})  # fmt: skip
    try:
        await discovery.add(session, on, candidate(doi="10.1038/srep12277"), pdf_dir)
    finally:
        await client.aclose()

    [request] = epmc
    assert request.url.params["query"] == 'DOI:"10.1038/srep12277"'


async def test_no_pmcid_asks_neither_the_bucket_nor_europe_pmc(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/closed", 403)

    with pytest.raises(Conflict):
        found = candidate(doi="10.5555/no-pmc", pdf_urls=["https://pdf.example/closed"])
        await discovery.add(session, discovery_fakes.providers, found, pdf_dir)  # Europe PMC off in these fakes

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/closed"]
