import json
from dataclasses import replace

import httpx
import pytest
from conftest import recorded_discovery

from app.core import discovery
from app.core.discovery import Candidate
from app.core.errors import Conflict
from app.models import Paper

pytestmark = pytest.mark.anyio

BERT_DOI = "10.18653/v1/n19-1423"
BERT_S2_ID = "df2b0e26d0599ce3e70df8a9da02e51594e0e992"
BATCH = "/graph/v1/paper/batch"


async def add_paper(session, **fields) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", **{"title": "A library paper", **fields})
    session.add(paper)
    await session.flush()
    return paper


# --- mark_in_library ---


async def test_candidates_are_marked_by_openalex_id_doi_in_any_case_or_arxiv_doi(session):
    by_id = await add_paper(session, openalex_id="W9000000001")
    by_doi = await add_paper(session, doi="10.5555/M19-Case")
    by_arxiv = await add_paper(session, doi="10.48550/arxiv.2411.18021")
    candidates = [
        Candidate(title="a", openalex_id="W9000000001"),
        Candidate(title="b", doi="10.5555/m19-case"),
        Candidate(title="c", arxiv_id="2411.18021"),
        Candidate(title="d", doi="10.5555/m19-elsewhere", openalex_id="W9000000002", arxiv_id="9999.00001"),
    ]

    marked = await discovery.mark_in_library(session, candidates)

    assert [c.paper_id for c in marked] == [by_id.id, by_doi.id, by_arxiv.id, None]
    assert [c.paper_id for c in candidates] == [None] * 4  # new candidates, the inputs unchanged


# --- search ---


async def test_a_title_search_asks_openalex_then_one_semantic_scholar_batch(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", recorded_discovery("openalex_search_bert"))
    discovery_fakes.s2.reply(BATCH, 200, json=recorded_discovery("s2_batch_bert")[:1])

    results = await discovery.search(session, discovery_fakes.providers, "BERT pre-training")

    [openalex_request] = discovery_fakes.openalex.requests
    assert openalex_request.url.params["filter"] == "title.search:BERT pre-training"
    assert openalex_request.url.params["per-page"] == "10"
    [batch] = discovery_fakes.s2.requests
    assert json.loads(batch.read()) == {"ids": [f"DOI:{BERT_DOI}"]}  # the second result has no DOI
    assert results[0].arxiv_id == "1810.04805"
    assert results[0].pdf_urls[0] == "https://arxiv.org/pdf/1810.04805"
    assert len(results) == 2


async def test_a_doi_is_looked_up_not_searched(session, discovery_fakes):
    bert = recorded_discovery("openalex_search_bert")["results"][0]
    discovery_fakes.openalex.route(f"/works/doi:{BERT_DOI}", bert)
    discovery_fakes.s2.reply(BATCH, 200, json=[None])

    [result] = await discovery.search(session, discovery_fakes.providers, f"https://doi.org/{BERT_DOI.upper()}")

    assert result.openalex_id == "W2963341956"
    assert [r.url.path for r in discovery_fakes.openalex.requests] == [f"/works/doi:{BERT_DOI}"]


async def test_an_unknown_doi_finds_nothing(session, discovery_fakes):
    discovery_fakes.openalex.route("/works/doi:10.5555/m19-missing", httpx.Response(404, text="<!doctype html>"))

    assert await discovery.search(session, discovery_fakes.providers, "10.5555/m19-missing") == []
    assert discovery_fakes.s2.requests == []  # no DOIs, no batch


async def test_an_arxiv_id_is_looked_up_on_semantic_scholar_even_with_openalex_off(session, discovery_fakes):
    providers = replace(discovery_fakes.providers, openalex=None)
    discovery_fakes.s2.reply("/graph/v1/paper/arXiv:1810.04805", 200, json=recorded_discovery("s2_paper_arxiv_bert"))

    [result] = await discovery.search(session, providers, "arXiv:1810.04805v2")

    assert (result.doi, result.arxiv_id, result.s2_id) == (BERT_DOI, "1810.04805", BERT_S2_ID)
    assert result.pdf_urls[0] == "https://arxiv.org/pdf/1810.04805"
    assert discovery_fakes.openalex.requests == []


async def test_an_arxiv_id_semantic_scholar_does_not_know_finds_nothing(session, discovery_fakes):
    discovery_fakes.s2.reply("/graph/v1/paper/arXiv:9999.99999", 404, json={"error": "not found"})

    assert await discovery.search(session, discovery_fakes.providers, "9999.99999") == []


async def test_a_title_or_doi_search_needs_openalex(session, discovery_fakes):
    providers = replace(discovery_fakes.providers, openalex=None)

    for query in ("BERT", BERT_DOI):
        with pytest.raises(Conflict, match="OpenAlex is off"):
            await discovery.search(session, providers, query)
    assert discovery_fakes.s2.requests == []


async def test_busy_openalex_or_semantic_scholar_lookups_say_so(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", httpx.Response(429, json={"error": "rate limited"}))
    discovery_fakes.s2.reply("/graph/v1/paper/arXiv:1810.04805", 429, json={"code": "429"})

    with pytest.raises(Conflict, match="OpenAlex is busy"):
        await discovery.search(session, discovery_fakes.providers, "BERT")
    with pytest.raises(Conflict, match="Semantic Scholar is busy"):
        await discovery.search(session, discovery_fakes.providers, "1810.04805")


async def test_a_failing_batch_leaves_openalex_results_as_they_are(session, discovery_fakes):
    discovery_fakes.openalex.route("/works", recorded_discovery("openalex_search_bert"))
    discovery_fakes.s2.refuse(BATCH)

    results = await discovery.search(session, discovery_fakes.providers, "BERT")

    assert results[0].doi == BERT_DOI
    assert results[0].pdf_urls == []


async def test_search_results_already_in_the_library_are_marked(session, discovery_fakes):
    paper = await add_paper(session, openalex_id="W2963341956")
    discovery_fakes.openalex.route("/works", recorded_discovery("openalex_search_bert"))
    discovery_fakes.s2.reply(BATCH, 200, json=[None])

    results = await discovery.search(session, discovery_fakes.providers, "BERT")

    assert [r.paper_id for r in results] == [paper.id, None]


# --- similar ---


def recommendations_url(key: str) -> str:
    return f"/recommendations/v1/papers/forpaper/{key}"


def recommendations(*papers: dict) -> dict:
    return {"recommendedPapers": list(papers)}


def s2_paper(title: str, doi: str | None = None, arxiv_id: str | None = None) -> dict:
    ids = {key: value for key, value in (("DOI", doi), ("ArXiv", arxiv_id)) if value}
    return {
        "paperId": title.encode().hex()[:40].ljust(40, "0"),
        "title": title,
        "externalIds": ids,
        "openAccessPdf": {"url": ""},
    }


async def test_similar_papers_to_a_published_paper_ask_by_its_doi_and_leave_the_paper_itself_out(
    session, discovery_fakes
):
    paper = await add_paper(session, title="BERT", doi=BERT_DOI.upper())
    discovery_fakes.s2.reply(
        recommendations_url(f"DOI:{BERT_DOI}"),
        200,
        json=recommendations(
            s2_paper("A", "10.5555/m19-a"),
            s2_paper("Bert!", "10.5555/m19-other"),
            s2_paper("B", BERT_DOI),
            s2_paper("C"),
            s2_paper("D"),
        ),
    )

    results = await discovery.similar(session, discovery_fakes.providers, paper, limit=2)

    assert [r.title for r in results] == ["A", "C"]  # "Bert!" has the paper's title, "B" its DOI
    [request] = discovery_fakes.s2.requests
    assert request.url.params["from"] == "all-cs"
    assert request.url.params["limit"] == "3"


async def test_similar_papers_to_an_arxiv_paper_ask_by_its_arxiv_id(session, discovery_fakes):
    paper = await add_paper(session, doi="10.48550/arxiv.2411.18021")
    discovery_fakes.s2.reply(recommendations_url("arXiv:2411.18021"), 200, json=recommendations(s2_paper("A")))

    assert [r.title for r in await discovery.similar(session, discovery_fakes.providers, paper)] == ["A"]


async def test_similar_papers_to_a_paper_without_a_doi_find_it_by_title_first(session, discovery_fakes):
    paper = await add_paper(session, title="BERT: Pre-training of Deep Bidirectional Transformers")
    discovery_fakes.s2.reply("/graph/v1/paper/search/match", 200, json=recorded_discovery("s2_match_bert"))
    discovery_fakes.s2.reply(
        recommendations_url(BERT_S2_ID), 200, json=recommendations(s2_paper("A", arxiv_id="2003.07000"))
    )

    [result] = await discovery.similar(session, discovery_fakes.providers, paper)

    assert result.pdf_urls == ["https://arxiv.org/pdf/2003.07000"]
    assert discovery_fakes.s2.requests[0].url.params["query"] == paper.title


async def test_a_paper_semantic_scholar_does_not_know_has_no_suggestions(session, discovery_fakes):
    no_title_match = await add_paper(session, title="zzqx qqzv")
    unknown_doi = await add_paper(session, doi="10.9999/not-in-s2")
    no_match = recorded_discovery("s2_match_none")
    unknown = recorded_discovery("s2_unknown_paper")
    discovery_fakes.s2.reply("/graph/v1/paper/search/match", no_match["status"], json=no_match["body"])
    discovery_fakes.s2.reply(recommendations_url("DOI:10.9999/not-in-s2"), unknown["status"], json=unknown["body"])

    for paper in (no_title_match, unknown_doi):
        with pytest.raises(Conflict, match="doesn't know this paper"):
            await discovery.similar(session, discovery_fakes.providers, paper)


async def test_busy_semantic_scholar_suggestions_say_so(session, discovery_fakes):
    paper = await add_paper(session, doi=BERT_DOI)
    discovery_fakes.s2.reply(recommendations_url(f"DOI:{BERT_DOI}"), 429, json={"code": "429"})

    with pytest.raises(Conflict, match="Semantic Scholar is busy"):
        await discovery.similar(session, discovery_fakes.providers, paper)


async def test_suggestions_already_in_the_library_are_marked(session, discovery_fakes):
    paper = await add_paper(session, doi=BERT_DOI)
    owned = await add_paper(session, doi="10.48550/arxiv.2003.07000")
    discovery_fakes.s2.reply(recommendations_url(f"DOI:{BERT_DOI}"), 200, json=recorded_discovery("s2_recommend_bert"))

    results = await discovery.similar(session, discovery_fakes.providers, paper)

    assert {r.arxiv_id: r.paper_id for r in results}["2003.07000"] == owned.id
