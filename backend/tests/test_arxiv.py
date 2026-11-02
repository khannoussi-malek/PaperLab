import httpx
import pytest
from conftest import DISCOVERY_FIXTURES, FakeProvider

from app.providers import arxiv

pytestmark = pytest.mark.anyio

ATOM = '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">{}</feed>'


def recorded_feed(name: str) -> str:
    """An Atom body recorded by tests/fixtures/discovery/record.py."""
    return (DISCOVERY_FIXTURES / f"{name}.xml").read_text()


@pytest.fixture
async def arxiv_api():
    fake = FakeProvider()
    fake.client = arxiv.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_title_search_ands_the_title_words_in_the_title_field(arxiv_api):
    arxiv_api.reply("/api/query", 200, text=recorded_feed("arxiv_search_bert"))

    entries = await arxiv.search(arxiv_api.client, "Pre-training of Deep Bidirectional Transformers", 3)

    assert entries[0]["arxiv_id"] == "1810.04805"
    [request] = arxiv_api.requests
    assert (
        request.url.params["search_query"]
        == "ti:pre AND ti:training AND ti:deep AND ti:bidirectional AND ti:transformers"
    )
    assert request.url.params["max_results"] == "3"


@pytest.mark.parametrize(
    ("title", "words"),
    [
        # arXiv matches nothing for `ti:is` or `ti:the`, which would empty the whole AND query.
        ("Attention Is All You Need", ["attention", "all", "you", "need"]),
        # CORE's parser reads and/or/not as operators in any case; arXiv answers 400 for `ti:AND`.
        ("BERT AND GPT or Not", ["bert", "gpt"]),
        (" ".join(f"word{n}" for n in range(13)), [f"word{n}" for n in range(12)]),
    ],
    ids=["stopwords", "operators", "at most twelve"],
)
def test_title_words_are_lowercase_without_stopwords_and_at_most_twelve(title, words):
    assert arxiv.title_words(title) == words


@pytest.mark.parametrize("title", ["", " — : ", "To be or not to be"])
async def test_a_title_with_no_search_words_sends_nothing(arxiv_api, title):
    assert await arxiv.search(arxiv_api.client, title, 10) == []
    assert arxiv_api.requests == []


async def test_get_parses_the_entry_without_its_version(arxiv_api):
    arxiv_api.reply("/api/query", 200, text=recorded_feed("arxiv_get_bert"))

    entry = await arxiv.get(arxiv_api.client, "1810.04805")

    assert entry.pop("abstract").startswith("We introduce a new language representation model called BERT")
    assert entry == {
        "arxiv_id": "1810.04805",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
        "year": 2018,
        "doi": None,
        "journal_ref": None,
    }
    assert arxiv_api.requests[0].url.params["id_list"] == "1810.04805"


async def test_an_old_style_id_whitespace_in_the_title_and_the_doi_are_normalised(arxiv_api):
    entry = """<entry>
      <id>http://arxiv.org/abs/hep-th/9901001v3</id>
      <title>String Junctions and Their
        Duals in Heterotic String Theory</title>
      <published>1999-01-01T01:01:10Z</published>
      <author><name>Yosuke Imamura</name></author>
      <arxiv:doi>10.1143/PTP.101.1155</arxiv:doi>
    </entry>"""
    arxiv_api.reply("/api/query", 200, text=ATOM.format(entry))

    assert await arxiv.get(arxiv_api.client, "hep-th/9901001") == {
        "arxiv_id": "hep-th/9901001",
        "title": "String Junctions and Their Duals in Heterotic String Theory",
        "authors": ["Yosuke Imamura"],
        "year": 1999,
        "doi": "10.1143/ptp.101.1155",
        "journal_ref": None,
        "abstract": None,
    }


async def test_an_empty_author_name_is_dropped(arxiv_api):
    entry = """<entry>
      <id>http://arxiv.org/abs/1810.04805v2</id>
      <title>BERT</title>
      <published>2018-10-11T00:00:00Z</published>
      <author><name/></author>
      <author><name>Jacob Devlin</name></author>
    </entry>"""
    arxiv_api.reply("/api/query", 200, text=ATOM.format(entry))

    entry = await arxiv.get(arxiv_api.client, "1810.04805")

    assert entry["authors"] == ["Jacob Devlin"]


async def test_an_id_arxiv_does_not_have_is_none(arxiv_api):
    # A well-formed unknown ID is an empty feed.
    arxiv_api.reply("/api/query", 200, text=recorded_feed("arxiv_get_missing"))

    assert await arxiv.get(arxiv_api.client, "2609.99999") is None


async def test_a_malformed_id_is_none_not_its_error_entry(arxiv_api):
    # arXiv answers 400 with a feed whose one entry is titled "Error", e.g. for hep-th/9999999.
    arxiv_api.reply("/api/query", 400, text=recorded_feed("arxiv_get_malformed"))

    assert await arxiv.get(arxiv_api.client, "hep-th/9999999") is None


async def test_an_error_entry_in_a_200_feed_is_not_a_paper(arxiv_api):
    arxiv_api.reply("/api/query", 200, text=recorded_feed("arxiv_get_malformed"))

    assert await arxiv.search(arxiv_api.client, "BERT", 3) == []


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, "<!doctype html><html><body>proxy login"),
        (200, "<html><body/></html>"),
        (503, "busy"),
        (429, "Rate exceeded."),
    ],
    ids=["not xml", "xml but not atom", "server error", "rate limited"],
)
async def test_failures_raise_an_httpx_error(arxiv_api, status, body):
    arxiv_api.reply("/api/query", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await arxiv.search(arxiv_api.client, "BERT", 3)
    with pytest.raises(httpx.HTTPError):
        await arxiv.get(arxiv_api.client, "1810.04805")


def _atom_entry(arxiv_id: str, abstract: str) -> str:
    return (f"<entry><id>http://arxiv.org/abs/{arxiv_id}v1</id><title>T {arxiv_id}</title>"
            f"<published>2023-01-02T00:00:00Z</published><summary>{abstract}</summary></entry>")


async def test_get_many_parses_several_entries_and_skips_errors(arxiv_api):
    body = ATOM.format(
        _atom_entry("2301.00001", "First.")
        + '<entry><id>https://arxiv.org/api/errors#incorrect_id_format_for_2301.9</id><title>Error</title>'
        "<summary>incorrect id format</summary></entry>" + _atom_entry("2301.00003", "Third.")
    )
    arxiv_api.reply("/api/query", 200, text=body)

    entries = await arxiv.get_many(arxiv_api.client, ["2301.00001", "2301.9", "2301.00003"])

    assert [(e["arxiv_id"], e["abstract"]) for e in entries] == [("2301.00001", "First."), ("2301.00003", "Third.")]
    [request] = arxiv_api.requests
    assert request.url.params["id_list"] == "2301.00001,2301.9,2301.00003"
    assert request.url.params["max_results"] == "3"


async def test_get_many_raises_on_an_error_status(arxiv_api):
    arxiv_api.reply("/api/query", 429, text="busy")
    with pytest.raises(httpx.HTTPStatusError):
        await arxiv.get_many(arxiv_api.client, ["2301.00001"])


def _feed(count: int, first: int = 0) -> str:
    entries = "".join(
        f"<entry><id>http://arxiv.org/abs/2601.{first + i:05d}v1</id><title>Paper {first + i}</title>"
        "<published>2026-01-01T00:00:00Z</published></entry>"
        for i in range(count)
    )
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'


def _paged(every_word: int, any_word: int):
    """arXiv with `every_word` AND matches and `any_word` OR matches; records each request."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        query, start = request.url.params["search_query"], int(request.url.params["start"])
        size = int(request.url.params["max_results"])
        total = any_word if " OR " in query else every_word
        seen.append(("or" if " OR " in query else "and", start))
        return httpx.Response(200, text=_feed(max(0, min(size, total - start)), start))

    return httpx.MockTransport(handler), seen


async def _all_pages(transport, topic: str) -> list[dict]:
    found, cursor = [], 0
    async with arxiv.new_client(transport=transport) as http:
        while cursor is not None:
            page, cursor = await arxiv.search_page(http, topic, 20, cursor)
            found += page
    return found


async def test_a_topic_with_enough_every_word_matches_never_asks_for_any_word_ones():
    transport, seen = _paged(every_word=214, any_word=291294)
    found = await _all_pages(transport, "creativity in software engineering")
    assert len(found) == 214 and {stage for stage, _ in seen} == {"and"}


async def test_a_thin_result_widens_to_the_top_of_the_any_word_list_only():
    transport, seen = _paged(every_word=1, any_word=367057)
    found = await _all_pages(transport, "software design creativity fixation")
    assert len(found) == 1 + arxiv.WIDEN_RESULTS
    assert seen == [("and", 0), ("or", 0), ("or", 20)]


async def test_a_single_word_topic_has_nothing_wider_to_ask():
    transport, seen = _paged(every_word=3, any_word=3)
    await _all_pages(transport, "creativity")
    assert seen == [("and", 0)]


async def test_a_short_any_word_list_ends_the_search():
    transport, seen = _paged(every_word=0, any_word=5)
    assert len(await _all_pages(transport, "mode collapse")) == 5
    assert seen == [("and", 0), ("or", 0)]
