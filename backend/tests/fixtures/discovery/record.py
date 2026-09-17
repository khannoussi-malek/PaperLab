"""Re-records the responses the discovery tests serve, through the real providers. Needs the network; the test suite
never runs it. Semantic Scholar's recommendations drift, so tests assert only what holds for any recording (BERT's
IDs, the response shapes). The email goes to OpenAlex and Unpaywall. Name sources (openalex, s2, arxiv, crossref,
core, unpaywall) to re-record only those; every source is re-recorded by default.

    cd backend && uv run python -m tests.fixtures.discovery.record you@example.com [source ...]
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from app.providers import arxiv, core_ac, crossref, openalex, semantic_scholar, unpaywall
from app.providers.openalex import json_body

HERE = Path(__file__).parent
BERT_TITLE = "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
BERT_DOI = "10.18653/v1/n19-1423"
PREPRINT_ARXIV_ID = "2411.18021"  # an arXiv-only paper: OpenAlex's DOI for it is its arXiv DOI
ATTENTION_TITLE = "Attention Is All You Need"
NUMPY_DOI = "10.1038/s41586-020-2649-2"  # a publisher PDF and an arXiv PDF in Unpaywall

# Only the keys discovery reads. None keeps a value whole; a dict keeps those keys (in each item, for lists).
LOCATION = {"pdf_url": None, "landing_page_url": None}
WORK = {
    "id": None, "doi": None, "title": None, "publication_year": None, "cited_by_count": None,
    "authorships": {"author": {"display_name": None}},
    "primary_location": {"source": {"display_name": None}},
    "best_oa_location": LOCATION, "locations": LOCATION, "open_access": {"oa_url": None},
}  # fmt: skip
S2_PAPER = {
    "paperId": None, "title": None, "year": None, "venue": None, "authors": {"name": None}, "externalIds": None,
    "openAccessPdf": {"url": None}, "citationCount": None,
}  # fmt: skip
CROSSREF_ITEM = {
    "DOI": None, "title": None, "author": {"given": None, "family": None, "name": None}, "issued": None,
    "container-title": None, "is-referenced-by-count": None, "type": None,
}  # fmt: skip
CORE_WORK = {
    "id": None, "title": None, "authors": {"name": None}, "yearPublished": None, "doi": None, "arxivId": None,
    "downloadUrl": None, "sourceFulltextUrls": None, "citationCount": None,
}  # fmt: skip
UNPAYWALL = {"best_oa_location": {"url_for_pdf": None}, "oa_locations": {"url_for_pdf": None}}


def trim(value, shape):
    if shape is None or value is None:
        return value
    if isinstance(value, list):
        return [trim(item, shape) for item in value]
    return {key: trim(value.get(key), sub) for key, sub in shape.items() if key in value}


def save(name: str, body) -> None:
    (HERE / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    print("recorded", name)


def save_feed(name: str, feed: str) -> None:
    (HERE / f"{name}.xml").write_text(feed)
    print("recorded", name)


async def s2_get(http: httpx.AsyncClient, path: str, **params) -> httpx.Response:
    """The shared pool refuses often; wait and try again rather than record a 429."""
    for _ in range(10):
        response = await http.get(path, params=params)
        if response.status_code != 429:
            return response
        await asyncio.sleep(6)
    raise RuntimeError(f"Semantic Scholar kept answering 429 for {path}")


async def s2_post(http: httpx.AsyncClient, path: str, body: dict, **params) -> httpx.Response:
    for _ in range(10):
        response = await http.post(path, params=params, json=body)
        if response.status_code != 429:
            return response
        await asyncio.sleep(6)
    raise RuntimeError(f"Semantic Scholar kept answering 429 for {path}")


async def record_openalex(mailto: str) -> None:
    async with openalex.new_client(mailto) as oa:
        works = await openalex.search_works(oa, BERT_TITLE, per_page=2)
        save("openalex_search_bert", {"results": trim(works, WORK)})
        preprint = await openalex.get_work(oa, f"doi:10.48550/arxiv.{PREPRINT_ARXIV_ID}")
        save("openalex_work_arxiv_preprint", trim(preprint, WORK))


async def record_s2() -> None:
    async with semantic_scholar.new_client("") as s2:
        fields = semantic_scholar.PAPER_FIELDS
        pool = semantic_scholar.RECOMMENDATION_POOL
        recs = await s2_get(
            s2, f"/recommendations/v1/papers/forpaper/DOI:{BERT_DOI}", fields=fields, limit=4, **{"from": pool}
        )
        body = recs.raise_for_status().json()
        save("s2_recommend_bert", {"recommendedPapers": trim(body["recommendedPapers"], S2_PAPER)})
        unknown = await s2_get(s2, "/recommendations/v1/papers/forpaper/DOI:10.9999/not-in-s2", fields=fields)
        save("s2_unknown_paper", {"status": unknown.status_code, "body": unknown.json()})
        match = await s2_get(s2, "/graph/v1/paper/search/match", query=BERT_TITLE, fields="paperId")
        save("s2_match_bert", match.raise_for_status().json())
        paper = await s2_get(s2, "/graph/v1/paper/arXiv:1810.04805", fields=fields)
        save("s2_paper_arxiv_bert", trim(paper.raise_for_status().json(), S2_PAPER))
        batch = await s2_post(
            s2, "/graph/v1/paper/batch", {"ids": [f"DOI:{BERT_DOI}", "DOI:10.9999/not-in-s2"]}, fields=fields
        )
        save("s2_batch_bert", [trim(item, S2_PAPER) for item in batch.raise_for_status().json()])
        no_match = await s2_get(
            s2, "/graph/v1/paper/search/match", query="zzqx qqzv no such paper wvxq", fields="paperId"
        )
        save("s2_match_none", {"status": no_match.status_code, "body": no_match.json()})


async def record_arxiv() -> None:
    """Atom feeds are saved whole, as the provider received them, for the tests to parse again."""
    feeds: list[str] = []

    async def keep(response: httpx.Response) -> None:
        feeds.append((await response.aread()).decode())

    calls = {
        "arxiv_search_bert": lambda ax: arxiv.search(ax, "pre-training of deep bidirectional transformers", 3),
        "arxiv_get_bert": lambda ax: arxiv.get(ax, "1810.04805"),
        "arxiv_get_missing": lambda ax: arxiv.get(ax, "2609.99999"),
        "arxiv_get_malformed": lambda ax: arxiv.get(ax, "hep-th/9999999"),  # a 400 with an "Error" entry
    }
    async with arxiv.new_client() as ax:
        ax.event_hooks["response"] = [keep]
        for name, call in calls.items():
            await call(ax)
            save_feed(name, feeds[-1])
            await asyncio.sleep(3)  # arXiv asks for 3 seconds between requests


async def record_crossref() -> None:
    # No mailto: two requests fit the public pool's one a second.
    async with crossref.new_client(None) as cr:
        items = await crossref.search(cr, ATTENTION_TITLE.lower(), 5)
        save("crossref_search_attention", {"message": {"items": trim(items, CROSSREF_ITEM)}})
        await asyncio.sleep(1)
        save("crossref_work_bert", {"message": trim(await crossref.get_work(cr, BERT_DOI), CROSSREF_ITEM)})


async def record_core() -> None:
    async with core_ac.new_client(None) as core:
        works = await core_ac.search(core, ATTENTION_TITLE, 5)
        save("core_search_attention", {"results": trim(works, CORE_WORK)})


async def record_unpaywall(email: str) -> None:
    async with unpaywall.new_client(email) as up:
        for name, doi in [("unpaywall_numpy", NUMPY_DOI), ("unpaywall_bert", BERT_DOI)]:
            response = await up.get(f"/v2/{doi}")
            save(name, trim(json_body(response.raise_for_status()), UNPAYWALL))


async def main(email: str, sources: list[str]) -> None:
    recorders = {
        "openalex": lambda: record_openalex(email),
        "s2": record_s2,
        "arxiv": record_arxiv,
        "crossref": record_crossref,
        "core": record_core,
        "unpaywall": lambda: record_unpaywall(email),
    }
    for source in sources or recorders:
        await recorders[source]()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
