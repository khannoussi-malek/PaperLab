"""Re-records the OpenAlex and Semantic Scholar responses the discovery tests serve, through the real providers.
Needs the network; the test suite never runs it. Semantic Scholar's recommendations drift, so tests assert only what
holds for any recording (BERT's IDs, the response shapes).

    cd backend && uv run python -m tests.fixtures.discovery.record you@example.com
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from app.providers import openalex, semantic_scholar

HERE = Path(__file__).parent
BERT_TITLE = "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
BERT_DOI = "10.18653/v1/n19-1423"
PREPRINT_ARXIV_ID = "2411.18021"  # an arXiv-only paper: OpenAlex's DOI for it is its arXiv DOI

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


def trim(value, shape):
    if shape is None or value is None:
        return value
    if isinstance(value, list):
        return [trim(item, shape) for item in value]
    return {key: trim(value.get(key), sub) for key, sub in shape.items() if key in value}


def save(name: str, body) -> None:
    (HERE / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
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


async def main(mailto: str) -> None:
    async with openalex.new_client(mailto) as oa, semantic_scholar.new_client("") as s2:
        works = await openalex.search_works(oa, BERT_TITLE, per_page=2)
        save("openalex_search_bert", {"results": trim(works, WORK)})
        preprint = await openalex.get_work(oa, f"doi:10.48550/arxiv.{PREPRINT_ARXIV_ID}")
        save("openalex_work_arxiv_preprint", trim(preprint, WORK))

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


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
