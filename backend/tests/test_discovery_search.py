"""Search across every paper source that is on (M19.5, D72, D73, P7)."""

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.core import discovery
from app.core.errors import Conflict
from app.core.paper_sources import SourceSettings
from app.models import Paper

pytestmark = pytest.mark.anyio

BATCH = "/graph/v1/paper/batch"
BERT = "BERT: Pre-training of Deep Bidirectional Transformers"
BERT_DOI = "10.18653/v1/n19-1423"


def work(title: str, doi: str | None = None, pdf_url: str | None = None, author: str = "Jacob Devlin") -> dict:
    location = {"pdf_url": pdf_url, "landing_page_url": None}
    return {
        "id": f"https://openalex.org/W{abs(hash(title)) % 10**9}",
        "doi": doi and f"https://doi.org/{doi}",
        "title": title,
        "publication_year": 2019,
        "authorships": [{"author": {"display_name": author}}],
        "best_oa_location": location if pdf_url else None,
        "locations": [location],
    }


def crossref_item(title: str, doi: str, kind: str = "proceedings-article") -> dict:
    return {"DOI": doi, "type": kind, "title": [title], "author": [{"given": "Jacob", "family": "Devlin"}]}


def atom(*entries: tuple[str, str, str]) -> str:
    """An arXiv feed of (arXiv id with version, title, author) entries."""
    body = "".join(
        f"<entry><id>http://arxiv.org/abs/{arxiv_id}</id><published>2018-10-11T00:00:00Z</published>"
        f"<title>{title}</title><author><name>{author}</name></author></entry>"
        for arxiv_id, title, author in entries
    )
    return f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">{body}</feed>'


def core_work(core_id: int, title: str, author: str, download_url: str = "") -> dict:
    return {
        "id": core_id,
        "title": title,
        "authors": [{"name": author}],
        "yearPublished": 2023,
        "downloadUrl": download_url,
    }


def params(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(str(request.url)).query).items()}


async def test_a_title_search_asks_every_title_source_that_is_on_and_merges_what_they_find(session, discovery_fakes):
    fakes = discovery_fakes
    fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})
    fakes.crossref.reply("/works", 200, json={"message": {"items": [
        crossref_item(BERT, BERT_DOI.upper()), crossref_item("All You Need Is LSD", "10.5040/lsd", kind="other")
    ]}})  # fmt: skip
    fakes.arxiv.reply("/api/query", 200, text=atom(("1810.04805v2", BERT, "Jacob Devlin")))
    fakes.core.reply("/v3/search/works/", 200, json={"results": [
        core_work(1, BERT, "Devlin, Jacob", "https://core.ac.uk/download/1.pdf"),
        core_work(2, BERT, "Someone, Else"),
    ]})  # fmt: skip
    fakes.s2.reply(BATCH, 200, json=[None])

    found = await discovery.search(session, fakes.turned_on("crossref", "arxiv", "core"), "BERT pre-training")

    assert found.notices == []
    assert [(r.sources, r.doi, r.core_id) for r in found.results] == [
        (("openalex", "crossref", "arxiv", "core"), BERT_DOI, "1"),
        (("core",), None, "2"),  # same title, no shared author: another paper
    ]
    assert found.results[0].pdf_urls == ["https://arxiv.org/pdf/1810.04805", "https://core.ac.uk/download/1.pdf"]
    [crossref_request] = fakes.crossref.requests
    assert params(crossref_request)["query.bibliographic"] == "BERT pre-training"
    [arxiv_request] = fakes.arxiv.requests
    assert params(arxiv_request)["search_query"] == "ti:bert AND ti:pre AND ti:training"
    [core_request] = fakes.core.requests
    assert params(core_request)["q"] == "title:(bert AND pre AND training)"


async def test_a_doi_asks_only_openalex_and_crossref(session, discovery_fakes):
    discovery_fakes.openalex.route(f"/works/doi:{BERT_DOI}", httpx.Response(404, text="<!doctype html>"))
    discovery_fakes.crossref.reply(f"/works/{BERT_DOI}", 200, json={"message": crossref_item(BERT, BERT_DOI)})
    discovery_fakes.s2.reply(BATCH, 200, json=[None])
    providers = discovery_fakes.turned_on("crossref", "arxiv", "core")

    [result] = (await discovery.search(session, providers, BERT_DOI)).results

    assert (result.sources, result.doi) == (("crossref",), BERT_DOI)
    assert discovery_fakes.arxiv.requests == discovery_fakes.core.requests == []


async def test_an_arxiv_id_asks_semantic_scholar_and_arxiv(session, discovery_fakes):
    discovery_fakes.s2.reply("/graph/v1/paper/arXiv:1810.04805", 404, json={"error": "Paper not found"})
    discovery_fakes.arxiv.reply("/api/query", 200, text=atom(("1810.04805v2", BERT, "Jacob Devlin")))
    providers = replace(discovery_fakes.turned_on("arxiv", "crossref"), openalex=None)

    [result] = (await discovery.search(session, providers, "arXiv:1810.04805")).results

    assert (result.sources, result.arxiv_id) == (("arxiv",), "1810.04805")
    assert params(discovery_fakes.arxiv.requests[0])["id_list"] == "1810.04805"
    assert discovery_fakes.crossref.requests == []


async def test_a_failing_source_is_a_notice_and_the_others_still_answer(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})
    discovery_fakes.crossref.reply("/works", 503, text="Service Unavailable")
    discovery_fakes.core.reply("/v3/search/works/", 401, json={"message": "The API key you provided is not valid."})
    discovery_fakes.s2.reply(BATCH, 200, json=[None])

    found = await discovery.search(session, discovery_fakes.turned_on("crossref", "core"), "BERT")

    assert [r.doi for r in found.results] == [BERT_DOI]
    assert found.notices == [
        "Crossref is busy or unreachable.",
        "CORE refused its API key. Check it in Settings → Paper sources.",
    ]


async def test_a_403_from_a_keyless_source_is_busy_not_a_key_refusal(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})
    discovery_fakes.crossref.reply("/works", 403, json={"message": "Forbidden"})
    discovery_fakes.s2.reply(BATCH, 200, json=[None])

    found = await discovery.search(session, discovery_fakes.turned_on("crossref"), "BERT")

    assert found.notices == ["Crossref is busy or unreachable."]


async def test_a_refused_semantic_scholar_key_is_a_notice_beside_arxiv_results(session, discovery_fakes):
    discovery_fakes.s2.reply("/graph/v1/paper/arXiv:1810.04805", 403, json={"message": "Forbidden"})
    discovery_fakes.arxiv.reply("/api/query", 200, text=atom(("1810.04805v2", BERT, "Jacob Devlin")))

    found = await discovery.search(session, discovery_fakes.turned_on("arxiv"), "1810.04805")

    assert [r.arxiv_id for r in found.results] == ["1810.04805"]
    assert found.notices == ["Semantic Scholar refused its API key. Check it in Settings → Paper sources."]


async def test_when_every_asked_source_fails_the_search_fails_with_their_notices(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", httpx.ConnectError("unreachable"))
    discovery_fakes.crossref.reply("/works", 429, json={"status": "error"})

    with pytest.raises(Conflict, match=r"^OpenAlex is busy or unreachable\. Crossref is busy or unreachable\.$"):
        await discovery.search(session, discovery_fakes.turned_on("crossref"), "BERT")


async def test_a_bug_in_one_source_is_raised_not_hidden_as_a_notice(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})
    discovery_fakes.core.reply("/v3/search/works/", 200, json={"totalHits": 0})  # no "results": not a busy service

    with pytest.raises(KeyError, match="results"):
        await discovery.search(session, discovery_fakes.turned_on("core"), "BERT")


async def test_unpaywall_is_asked_only_for_results_with_a_doi_and_no_pdf(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [
        work("No copy yet", "10.5555/none"), work("Has a copy", "10.5555/copy", "https://example.org/copy.pdf"),
        work("No DOI"),
    ]})  # fmt: skip
    discovery_fakes.s2.reply(BATCH, 200, json=[None, None])
    discovery_fakes.unpaywall.reply("/v2/10.5555/none", 200, json={
        "best_oa_location": {"url_for_pdf": "https://repository.example.org/none.pdf"}, "oa_locations": []
    })  # fmt: skip

    found = await discovery.search(session, discovery_fakes.turned_on("unpaywall"), "copy")

    assert [r.pdf_urls for r in found.results] == [
        ["https://repository.example.org/none.pdf"], ["https://example.org/copy.pdf"], []
    ]  # fmt: skip
    assert [r.url.path for r in discovery_fakes.unpaywall.requests] == ["/v2/10.5555/none"]


async def test_a_failing_unpaywall_lookup_leaves_its_result_as_it_is(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})
    discovery_fakes.s2.reply(BATCH, 200, json=[None])
    discovery_fakes.unpaywall.refuse(f"/v2/{BERT_DOI}")

    found = await discovery.search(session, discovery_fakes.turned_on("unpaywall"), "BERT")

    assert ([r.pdf_urls for r in found.results], found.notices) == ([[]], [])


async def test_an_unreachable_unpaywall_stops_asking_after_the_first_refusal(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [
        work("Paper One", "10.5555/one"), work("Paper Two", "10.5555/two"), work("Paper Three", "10.5555/three"),
    ]})  # fmt: skip
    discovery_fakes.s2.reply(BATCH, 200, json=[None, None, None])
    for doi in ("10.5555/one", "10.5555/two", "10.5555/three"):
        discovery_fakes.unpaywall.refuse(f"/v2/{doi}")

    found = await discovery.search(session, discovery_fakes.turned_on("unpaywall"), "paper")

    assert [r.pdf_urls for r in found.results] == [[], [], []]
    assert found.notices == []
    # Concurrency 5 lets all three take the semaphore before any of them raises, so the flag can't stop every
    # follow-up request; it only guarantees fewer than one per candidate.
    assert len(discovery_fakes.unpaywall.requests) < 3


async def test_without_semantic_scholar_no_batch_is_sent(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", {"results": [work(BERT, BERT_DOI)]})

    found = await discovery.search(session, replace(discovery_fakes.providers, s2=None), "BERT")

    assert [r.doi for r in found.results] == [BERT_DOI]
    assert discovery_fakes.s2.requests == []


async def test_similar_papers_need_semantic_scholar(session, discovery_fakes):
    with pytest.raises(Conflict, match="Semantic Scholar is off"):
        await discovery.similar(session, replace(discovery_fakes.providers, s2=None), Paper(title="x", doi=BERT_DOI))


async def test_suggestions_without_a_pdf_get_unpaywall_links(session, discovery_fakes):
    suggestion = {"paperId": "a" * 40, "title": "RoBERTa", "externalIds": {"DOI": "10.5555/roberta"}}
    discovery_fakes.s2.reply(
        f"/recommendations/v1/papers/forpaper/DOI:{BERT_DOI}", 200, json={"recommendedPapers": [suggestion]}
    )
    discovery_fakes.unpaywall.reply("/v2/10.5555/roberta", 200, json={
        "best_oa_location": None, "oa_locations": [{"url_for_pdf": None}, {"url_for_pdf": "https://example.org/r.pdf"}]
    })  # fmt: skip

    [result] = await discovery.similar(session, discovery_fakes.turned_on("unpaywall"), Paper(title=BERT, doi=BERT_DOI))

    assert result.pdf_urls == ["https://example.org/r.pdf"]


async def test_a_refused_semantic_scholar_key_is_a_conflict_for_similar(session, discovery_fakes):
    discovery_fakes.s2.reply(f"/recommendations/v1/papers/forpaper/DOI:{BERT_DOI}", 403, json={"message": "Forbidden"})

    with pytest.raises(Conflict, match="Semantic Scholar refused its API key. Check it in Settings → Paper sources."):
        await discovery.similar(session, discovery_fakes.turned_on(), Paper(title=BERT, doi=BERT_DOI))


async def test_each_source_that_is_on_gets_a_client_and_keys_travel_in_headers():
    sources = SourceSettings(
        contact_email="me@example.org",
        enabled={
            "openalex": True,
            "crossref": False,
            "semantic_scholar": True,
            "arxiv": True,
            "core": True,
            "unpaywall": True,
        },
        api_keys={"openalex": "oa-key-0123456789", "semantic_scholar": None, "core": "core-key-0123456789"},
    )

    providers = discovery.build_providers(sources)

    assert providers.crossref is None
    assert providers.openalex.headers["Authorization"] == "Bearer oa-key-0123456789"
    assert "oa-key" not in str(providers.openalex.params)
    assert providers.core.headers["Authorization"] == "Bearer core-key-0123456789"
    assert "x-api-key" not in providers.s2.headers
    assert providers.unpaywall.params["email"] == "me@example.org"
    await providers.aclose()


async def test_unpaywall_and_openalex_stay_off_by_default_and_without_an_email():
    providers = discovery.build_providers(SourceSettings())

    assert (providers.openalex, providers.unpaywall) == (None, None)
    assert None not in (providers.crossref, providers.s2, providers.arxiv, providers.core)
    await providers.aclose()
