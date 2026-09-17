import httpx
import pytest
from conftest import FakeProvider, recorded_discovery

from app.providers import semantic_scholar

pytestmark = pytest.mark.anyio

BERT_RECOMMENDATIONS = "/recommendations/v1/papers/forpaper/DOI:10.18653/v1/n19-1423"


@pytest.fixture
async def s2():
    fake = FakeProvider()
    fake.client = semantic_scholar.new_client("", transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_recommend_asks_the_all_cs_pool_for_the_fields_discovery_reads(s2):
    s2.reply(BERT_RECOMMENDATIONS, 200, json=recorded_discovery("s2_recommend_bert"))

    papers = await semantic_scholar.recommend(s2.client, "DOI:10.18653/v1/n19-1423", 4)

    assert [p["title"] for p in papers] == [
        p["title"] for p in recorded_discovery("s2_recommend_bert")["recommendedPapers"]
    ]
    [request] = s2.requests
    assert request.url.params["from"] == "all-cs"
    assert request.url.params["limit"] == "4"
    assert request.url.params["fields"] == semantic_scholar.PAPER_FIELDS
    assert "x-api-key" not in request.headers


async def test_an_api_key_is_sent_as_a_header():
    fake = FakeProvider()
    fake.reply(BERT_RECOMMENDATIONS, 200, json={"recommendedPapers": []})
    async with semantic_scholar.new_client("secret-key", transport=fake.transport) as client:
        await semantic_scholar.recommend(client, "DOI:10.18653/v1/n19-1423", 1)

    assert fake.requests[0].headers["x-api-key"] == "secret-key"


async def test_a_paper_semantic_scholar_does_not_know_has_no_recommendations(s2):
    unknown = recorded_discovery("s2_unknown_paper")
    s2.reply("/recommendations/v1/papers/forpaper/DOI:10.9999/not-in-s2", unknown["status"], json=unknown["body"])

    assert await semantic_scholar.recommend(s2.client, "DOI:10.9999/not-in-s2", 4) is None


async def test_a_busy_shared_pool_raises(s2):
    s2.reply(BERT_RECOMMENDATIONS, 429, json={"message": "Too Many Requests", "code": "429"})

    with pytest.raises(httpx.HTTPStatusError):
        await semantic_scholar.recommend(s2.client, "DOI:10.18653/v1/n19-1423", 4)


async def test_a_malformed_body_raises_an_http_error(s2):
    s2.reply(BERT_RECOMMENDATIONS, 200, text="<html>proxy login</html>")

    with pytest.raises(httpx.HTTPError):
        await semantic_scholar.recommend(s2.client, "DOI:10.18653/v1/n19-1423", 4)


async def test_match_title_returns_the_best_match_id_or_none(s2):
    s2.reply("/graph/v1/paper/search/match", 200, json=recorded_discovery("s2_match_bert"))
    assert await semantic_scholar.match_title(s2.client, "BERT") == "df2b0e26d0599ce3e70df8a9da02e51594e0e992"
    assert s2.requests[0].url.params["query"] == "BERT"

    no_match = recorded_discovery("s2_match_none")
    s2.reply("/graph/v1/paper/search/match", no_match["status"], json=no_match["body"])
    assert await semantic_scholar.match_title(s2.client, "zzqx qqzv") is None


async def test_get_paper_by_arxiv_id_or_none(s2):
    s2.reply("/graph/v1/paper/arXiv:1810.04805", 200, json=recorded_discovery("s2_paper_arxiv_bert"))
    s2.reply("/graph/v1/paper/arXiv:9999.99999", 404, json={"error": "Paper with id arXiv:9999.99999 not found"})

    assert (await semantic_scholar.get_paper(s2.client, "arXiv:1810.04805"))["externalIds"]["ArXiv"] == "1810.04805"
    assert await semantic_scholar.get_paper(s2.client, "arXiv:9999.99999") is None


async def test_get_papers_posts_every_key_once_and_keeps_their_order(s2):
    s2.reply("/graph/v1/paper/batch", 200, json=recorded_discovery("s2_batch_bert"))

    papers = await semantic_scholar.get_papers(s2.client, ["DOI:10.18653/v1/n19-1423", "DOI:10.9999/not-in-s2"])

    assert papers[0]["externalIds"]["ArXiv"] == "1810.04805"
    assert papers[1] is None
    [request] = s2.requests
    assert request.method == "POST"
    assert request.read() == b'{"ids":["DOI:10.18653/v1/n19-1423","DOI:10.9999/not-in-s2"]}'


async def test_get_papers_with_no_keys_sends_nothing(s2):
    assert await semantic_scholar.get_papers(s2.client, []) == []
    assert s2.requests == []


async def test_a_batch_answer_that_is_not_a_list_raises_an_http_error(s2):
    s2.reply("/graph/v1/paper/batch", 200, json={"error": "unexpected"})

    with pytest.raises(httpx.HTTPError):
        await semantic_scholar.get_papers(s2.client, ["DOI:10.18653/v1/n19-1423"])
