import httpx
import pytest

from app.providers import arxiv, crossref, core_ac, semantic_scholar, openalex

pytestmark = pytest.mark.anyio


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


async def test_semantic_scholar_search_page_uses_offset(monkeypatch):
    seen_offsets = []

    async def fake_get(self, url, params=None, **kwargs):
        seen_offsets.append(params["offset"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"total": 0, "data": [], "next": None}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as http:
        await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=0)
        await semantic_scholar.search_page(http, "transformer", page_size=20, cursor=20)
    assert seen_offsets == [0, 20]


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
