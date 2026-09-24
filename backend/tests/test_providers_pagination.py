import httpx
import pytest

from app.providers import arxiv, crossref, core_ac, semantic_scholar, openalex

pytestmark = pytest.mark.anyio


# --- arxiv ------------------------------------


async def test_arxiv_search_page_advances_start(monkeypatch):
    seen_starts = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_starts.append(params["start"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, text="<feed xmlns='http://www.w3.org/2005/Atom'></feed>", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await arxiv.search_page(http, "transformer", page_size=20, cursor=0)
        await arxiv.search_page(http, "transformer", page_size=20, cursor=20)
    assert seen_starts == [0, 20]


async def test_arxiv_next_cursor_when_page_is_full(monkeypatch):
    """arXiv signals more data by returning a full-sized page."""
    full_page = """<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
        <entry><id>https://arxiv.org/abs/2301.00001v1</id><title>Paper 1</title><published>2023-01-01T00:00:00Z</published></entry>
        <entry><id>https://arxiv.org/abs/2301.00002v1</id><title>Paper 2</title><published>2023-01-02T00:00:00Z</published></entry>
    </feed>"""

    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, text=full_page, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await arxiv.search_page(http, "learning", page_size=2, cursor=0)

    assert len(entries) == 2
    assert next_cursor == 2  # cursor + page_size because page is full-sized


async def test_arxiv_next_cursor_when_page_is_short(monkeypatch):
    """arXiv signals no more data by returning a short page."""
    short_page = """<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
        <entry><id>https://arxiv.org/abs/2301.00001v1</id><title>Paper 1</title><published>2023-01-01T00:00:00Z</published></entry>
    </feed>"""

    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, text=short_page, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await arxiv.search_page(http, "learning", page_size=2, cursor=10)

    assert len(entries) == 1
    assert next_cursor is None  # page is short, no more data


# --- core_ac ------------------------------------


async def test_core_ac_search_page_uses_offset(monkeypatch):
    seen_offsets = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_offsets.append(params["offset"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"totalHits": 0, "results": []}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await core_ac.search_page(http, "transformer", page_size=20, cursor=0)
        await core_ac.search_page(http, "transformer", page_size=20, cursor=20)
    assert seen_offsets == [0, 20]


async def test_core_ac_next_cursor_when_more_data_available(monkeypatch):
    """CORE signals more data via totalHits comparison."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        # totalHits > cursor + page_size means more data available
        return httpx.Response(200, json={"totalHits": 100, "results": [{"id": "1"}, {"id": "2"}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await core_ac.search_page(http, "transformer", page_size=20, cursor=0)

    assert len(entries) == 2
    assert next_cursor == 20  # cursor + page_size < totalHits


async def test_core_ac_next_cursor_when_exhausted(monkeypatch):
    """CORE signals no more data when cursor + page_size >= totalHits."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"totalHits": 50, "results": [{"id": "1"}]}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await core_ac.search_page(http, "transformer", page_size=20, cursor=40)

    assert len(entries) == 1
    assert next_cursor is None  # cursor + page_size >= totalHits


# --- crossref ------------------------------------


async def test_crossref_search_page_uses_offset(monkeypatch):
    seen_offsets = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_offsets.append(params["offset"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"message": {"items": []}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await crossref.search_page(http, "transformer", page_size=20, cursor=0)
        await crossref.search_page(http, "transformer", page_size=20, cursor=20)
    assert seen_offsets == [0, 20]


async def test_crossref_next_cursor_when_page_is_full(monkeypatch):
    """Crossref signals more data by returning a full-sized page."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={"message": {"items": [{"DOI": "1"}, {"DOI": "2"}]}},
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await crossref.search_page(http, "transformer", page_size=2, cursor=0)

    assert len(entries) == 2
    assert next_cursor == 2  # cursor + page_size because page is full-sized


async def test_crossref_next_cursor_when_page_is_short(monkeypatch):
    """Crossref signals no more data by returning a short page."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={"message": {"items": [{"DOI": "1"}]}},
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await crossref.search_page(http, "transformer", page_size=2, cursor=10)

    assert len(entries) == 1
    assert next_cursor is None  # page is short, no more data


# --- semantic_scholar ------------------------------------


async def test_semantic_scholar_search_page_uses_offset(monkeypatch):
    seen_offsets = []
    seen_fields = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_offsets.append(params["offset"])
        seen_fields.append(params["fields"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"total": 0, "data": [], "next": None}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=0)
        await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=20)
    assert seen_offsets == [0, 20]
    # A bare `",".join(PAPER_FIELDS)` on the (string, not list) constant would insert a comma between every
    # character instead of the field names — this pins the real, whole-field-list value the request must carry.
    assert seen_fields == [semantic_scholar.PAPER_FIELDS, semantic_scholar.PAPER_FIELDS]


async def test_semantic_scholar_next_cursor_when_next_field_present(monkeypatch):
    """Semantic Scholar signals more data via presence of 'next' field."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={"total": 100, "data": [{"paperId": "1"}, {"paperId": "2"}], "next": 20},
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=0)

    assert len(entries) == 2
    assert next_cursor == 20  # body.get("next") is not None


async def test_semantic_scholar_next_cursor_when_next_field_absent(monkeypatch):
    """Semantic Scholar signals no more data by omitting 'next' field."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={"total": 50, "data": [{"paperId": "1"}]},  # no "next" field
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=20)

    assert len(entries) == 1
    assert next_cursor is None  # "next" field is missing


# --- openalex ------------------------------------


async def test_openalex_search_page_uses_page_number(monkeypatch):
    seen_pages = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_pages.append(params["page"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"meta": {"count": 0}, "results": []}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await openalex.search_page(http, "transformer", page_size=20, cursor=1)
        await openalex.search_page(http, "transformer", page_size=20, cursor=2)
    assert seen_pages == [1, 2]


async def test_openalex_next_cursor_when_more_data_available(monkeypatch):
    """OpenAlex signals more data via meta.count comparison with cursor * page_size."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        # cursor * page_size < meta.count means more data
        return httpx.Response(
            200,
            json={"meta": {"count": 100}, "results": [{"id": "W1"}, {"id": "W2"}]},
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await openalex.search_page(http, "transformer", page_size=20, cursor=1)

    assert len(entries) == 2
    assert next_cursor == 2  # cursor + 1 because 1 * 20 < 100


async def test_openalex_next_cursor_when_exhausted(monkeypatch):
    """OpenAlex signals no more data when cursor * page_size >= meta.count."""
    async def fake_get(self, url, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={"meta": {"count": 50}, "results": [{"id": "W1"}]},
            request=request
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        entries, next_cursor = await openalex.search_page(http, "transformer", page_size=20, cursor=3)

    assert len(entries) == 1
    assert next_cursor is None  # 3 * 20 >= 50
