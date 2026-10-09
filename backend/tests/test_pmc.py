# ruff: noqa: E501 -- inline XML fixtures recorded verbatim from a live PMC efetch; reflowing them to fit
# the line length risks corrupting the text content the parser reads.
import httpx
import pytest
from conftest import FakeProvider

from app.providers import pmc

pytestmark = pytest.mark.anyio

# Trimmed to the fields this module reads, recorded live against NCBI's efetch on 2026-10-09
# (PMC13647476, "Protein-Ratio Rheostats...", Bioessays 2026) -- includes the <abstract><title> label
# this module must skip, and a plain <pub-date> (no pub-type attribute) like the real record has.
ONE_ARTICLE = """<pmc-articleset>
<article><front><article-meta><article-id pub-id-type="pmcid">PMC13647476</article-id><article-id pub-id-type="pmid">42847424</article-id><article-id pub-id-type="doi">10.1002/bies.70195</article-id><title-group><article-title>Protein-Ratio Rheostats</article-title></title-group><contrib-group><contrib contrib-type="author"><name><surname>Subramanian</surname><given-names>Subbaya</given-names></name></contrib><contrib contrib-type="author"><name><surname>Kartha</surname><given-names>Reena V.</given-names></name></contrib></contrib-group><pub-date><year>2026</year></pub-date><abstract><title>ABSTRACT</title><p>Cellular function depends on protein ratios.</p></abstract></article-meta></front></article>
</pmc-articleset>"""

TWO_ARTICLES = ONE_ARTICLE.replace(
    "</pmc-articleset>",
    '<article><front><article-meta><article-id pub-id-type="pmcid">PMC13646509</article-id><title-group><article-title>Second Paper</article-title></title-group><contrib-group><contrib contrib-type="author"><name><surname>Lee</surname><given-names>Grace</given-names></name></contrib></contrib-group><pub-date><year>2025</year></pub-date></article-meta></front></article>\n</pmc-articleset>',
)

UNKNOWN_ID = '<pmc-articleset><error id="999999999999">The following PMCID is not available: 999999999999</error></pmc-articleset>'


@pytest.fixture
async def pmc_api():
    fake = FakeProvider()
    fake.client = pmc.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_does_esearch_then_one_batched_efetch(pmc_api):
    pmc_api.reply(
        "/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "2", "idlist": ["13647476", "13646509"]}}
    )
    pmc_api.reply("/entrez/eutils/efetch.fcgi", 200, text=TWO_ARTICLES)

    entries = await pmc.search(pmc_api.client, "protein ratio", 10)

    assert [e["pmcid"] for e in entries] == ["13647476", "13646509"]
    [esearch_request, efetch_request] = pmc_api.requests
    assert esearch_request.url.params["term"] == "protein ratio"
    assert esearch_request.url.params["sort"] == "relevance"
    assert efetch_request.url.params["id"] == "13647476,13646509"  # one batched call, not two


async def test_search_with_no_results_never_calls_efetch(pmc_api):
    pmc_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "0", "idlist": []}})

    assert await pmc.search(pmc_api.client, "zzqqxx no such term", 10) == []
    assert len(pmc_api.requests) == 1  # esearch only


async def test_get_parses_the_full_record_and_skips_the_abstract_title_label(pmc_api):
    pmc_api.reply("/entrez/eutils/efetch.fcgi", 200, text=ONE_ARTICLE)

    entry = await pmc.get(pmc_api.client, "13647476")

    assert entry == {
        "pmcid": "13647476",
        "pmid": "42847424",
        "title": "Protein-Ratio Rheostats",
        "authors": ["Subbaya Subramanian", "Reena V. Kartha"],
        "year": 2026,
        "doi": "10.1002/bies.70195",
        "abstract": "Cellular function depends on protein ratios.",  # not "ABSTRACT Cellular function..."
    }


async def test_a_pmc_id_pmc_does_not_know_is_none(pmc_api):
    pmc_api.reply("/entrez/eutils/efetch.fcgi", 200, text=UNKNOWN_ID)

    assert await pmc.get(pmc_api.client, "999999999999") is None


async def test_a_record_with_no_pmid_doi_or_abstract_maps_without_them(pmc_api):
    bare = """<pmc-articleset>
<article><front><article-meta><article-id pub-id-type="pmcid">PMC1</article-id><title-group><article-title>Bare Record</article-title></title-group><contrib-group><contrib contrib-type="author"><name><surname>Smith</surname><given-names>Jo</given-names></name></contrib></contrib-group><pub-date><year>2020</year></pub-date></article-meta></front></article>
</pmc-articleset>"""
    pmc_api.reply("/entrez/eutils/efetch.fcgi", 200, text=bare)

    entry = await pmc.get(pmc_api.client, "1")

    assert entry == {
        "pmcid": "1", "pmid": None, "title": "Bare Record", "authors": ["Jo Smith"], "year": 2020,
        "doi": None, "abstract": None,
    }  # fmt: skip


async def test_new_client_sends_the_api_key_as_a_query_param_when_set(pmc_api):
    client = pmc.new_client(api_key="test-ncbi-key", transport=pmc_api.transport)
    pmc_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "0", "idlist": []}})

    await pmc.search(client, "x", 1)

    assert pmc_api.requests[0].url.params["api_key"] == "test-ncbi-key"
    await client.aclose()


async def test_an_esearch_error_reply_raises_httpx_error_not_keyerror(pmc_api):
    pmc_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"ERROR": "Empty term provided."}})

    with pytest.raises(httpx.HTTPError):
        await pmc.search(pmc_api.client, "", 1)


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(pmc_api, status, body):
    pmc_api.reply("/entrez/eutils/esearch.fcgi", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await pmc.search(pmc_api.client, "x", 1)
