# ruff: noqa: E501 -- inline XML/JSON fixtures recorded verbatim from NCBI; reflowing them to fit the line
# length risks corrupting text content the parser reads (only ArticleTitle is whitespace-normalized).
import httpx
import pytest
from conftest import FakeProvider

from app.providers import pubmed

pytestmark = pytest.mark.anyio

# One real PubMedArticle, trimmed to the fields this module reads, recorded live against NCBI's efetch on
# 2026-10-09 (PMID 42825172 — a real, stable record; see this plan's Global Constraints for the shape).
ONE_ARTICLE = """<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID Version="1">42825172</PMID><Article><Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal><ArticleTitle>Are You PREPAREd? A Structured Approach to Support Safe and Confident Transitions to After-Hours Care.</ArticleTitle><ELocationID EIdType="doi" ValidYN="Y">10.5334/pme.2504</ELocationID><Abstract><AbstractText Label="BACKGROUND" NlmCategory="UNASSIGNED">Early after-hours work represents a demanding transition.</AbstractText><AbstractText Label="GOAL" NlmCategory="UNASSIGNED">PREPARE supports new graduates.</AbstractText></Abstract><AuthorList CompleteYN="Y"><Author ValidYN="Y"><LastName>Baten</LastName><ForeName>Anique</ForeName></Author><Author ValidYN="Y"><LastName>Pool</LastName><ForeName>Inge A</ForeName></Author></AuthorList></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""

TWO_ARTICLES = ONE_ARTICLE.replace(
    "</PubmedArticleSet>",
    '<PubmedArticle><MedlineCitation><PMID Version="1">42786991</PMID><Article><Journal><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal><ArticleTitle>Second Paper.</ArticleTitle><AuthorList><Author><LastName>Lammerts</LastName><ForeName>Jesse</ForeName></Author></AuthorList></Article></MedlineCitation></PubmedArticle>\n</PubmedArticleSet>',
)

EMPTY_SET = "<PubmedArticleSet></PubmedArticleSet>"

# Carries inline markup PubMed uses for species/genes (<i>) and a DOI recorded only in PubmedData's own
# ArticleIdList (not ELocationID) — the two real shapes Fix 1 (C1) and Fix 3 (I3) exist to handle. Not
# itself a live-recorded record; built from the live-verified shapes the final review found.
MARKED_UP_ARTICLE = """<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>5</PMID><Article><Journal><JournalIssue><PubDate><Year>2005</Year></PubDate></JournalIssue></Journal><ArticleTitle>Engineering <i>Escherichia coli</i> for Improved Yield</ArticleTitle><Abstract><AbstractText>Expression of <i>lacZ</i> under control of P<sub>tac</sub> increased yield.</AbstractText></Abstract><AuthorList><Author><LastName>Lee</LastName><ForeName>Grace</ForeName></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">5</ArticleId><ArticleId IdType="doi">10.1000/marked.5</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
async def pubmed_api():
    fake = FakeProvider()
    fake.client = pubmed.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_does_esearch_then_one_batched_efetch(pubmed_api):
    pubmed_api.reply(
        "/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "2", "idlist": ["42825172", "42786991"]}}
    )
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=TWO_ARTICLES)

    entries = await pubmed.search(pubmed_api.client, "transitions to practice", 10)

    assert [e["pmid"] for e in entries] == ["42825172", "42786991"]
    [esearch_request, efetch_request] = pubmed_api.requests
    assert esearch_request.url.params["term"] == "transitions to practice"
    assert esearch_request.url.params["retmax"] == "10"
    assert efetch_request.url.params["id"] == "42825172,42786991"  # one batched call, not two


async def test_search_with_no_results_never_calls_efetch(pubmed_api):
    pubmed_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "0", "idlist": []}})

    assert await pubmed.search(pubmed_api.client, "zzqqxx no such term", 10) == []
    assert len(pubmed_api.requests) == 1  # esearch only


async def test_get_parses_the_full_record(pubmed_api):
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=ONE_ARTICLE)

    entry = await pubmed.get(pubmed_api.client, "42825172")

    assert entry == {
        "pmid": "42825172",
        "title": "Are You PREPAREd? A Structured Approach to Support Safe and Confident Transitions to After-Hours Care.",
        "authors": ["Anique Baten", "Inge A Pool"],
        "year": 2026,
        "doi": "10.5334/pme.2504",
        "abstract": "Early after-hours work represents a demanding transition. PREPARE supports new graduates.",
    }
    assert pubmed_api.requests[0].url.params["id"] == "42825172"
    assert pubmed_api.requests[0].url.params["retmode"] == "xml"


async def test_a_pmid_pubmed_does_not_know_is_none(pubmed_api):
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=EMPTY_SET)

    assert await pubmed.get(pubmed_api.client, "999999999999") is None


async def test_a_record_with_no_doi_or_abstract_maps_without_them(pubmed_api):
    bare = """<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>1</PMID><Article><Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal><ArticleTitle>Bare Record.</ArticleTitle><AuthorList><Author><LastName>Smith</LastName><ForeName>Jo</ForeName></Author></AuthorList></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=bare)

    entry = await pubmed.get(pubmed_api.client, "1")

    assert entry == {
        "pmid": "1", "title": "Bare Record.", "authors": ["Jo Smith"], "year": 2020, "doi": None, "abstract": None,
    }  # fmt: skip


async def test_inline_markup_in_title_and_abstract_is_flattened_not_truncated(pubmed_api):
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=MARKED_UP_ARTICLE)

    entry = await pubmed.get(pubmed_api.client, "5")

    assert entry["title"] == "Engineering Escherichia coli for Improved Yield"
    assert entry["abstract"] == "Expression of lacZ under control of Ptac increased yield."


async def test_doi_falls_back_to_pubmeddata_articleidlist_when_elocationid_has_none(pubmed_api):
    pubmed_api.reply("/entrez/eutils/efetch.fcgi", 200, text=MARKED_UP_ARTICLE)

    entry = await pubmed.get(pubmed_api.client, "5")

    assert entry["doi"] == "10.1000/marked.5"


async def test_search_asks_for_relevance_sort(pubmed_api):
    pubmed_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "0", "idlist": []}})

    await pubmed.search(pubmed_api.client, "x", 1)

    assert pubmed_api.requests[0].url.params["sort"] == "relevance"


async def test_an_esearch_error_reply_raises_httpx_error_not_keyerror(pubmed_api):
    """NCBI answers HTTP 200 with an ERROR key (no idlist/count) for a malformed query, an empty term, or
    retstart past its 9,999-record ceiling — this must not escape as a bare KeyError, since discovery.py
    and workspace_search.py only catch httpx.HTTPError."""
    pubmed_api.reply(
        "/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"ERROR": "Empty term provided."}}
    )

    with pytest.raises(httpx.HTTPError):
        await pubmed.search(pubmed_api.client, "", 1)


async def test_new_client_sends_the_api_key_as_a_query_param_when_set(pubmed_api):
    client = pubmed.new_client(api_key="test-ncbi-key", transport=pubmed_api.transport)
    pubmed_api.reply("/entrez/eutils/esearch.fcgi", 200, json={"esearchresult": {"count": "0", "idlist": []}})

    await pubmed.search(client, "x", 1)

    assert pubmed_api.requests[0].url.params["api_key"] == "test-ncbi-key"
    await client.aclose()


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(pubmed_api, status, body):
    pubmed_api.reply("/entrez/eutils/esearch.fcgi", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await pubmed.search(pubmed_api.client, "x", 1)
