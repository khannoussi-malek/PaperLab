"""Re-records the responses tests/test_references_providers.py serves, through the M7.5 prototype's providers.
Needs the network; the test suite never runs it.

    cd backend && uv run python /path/to/proto75/tests/fixtures/references/record.py you@example.com
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).parent
OVERLAY = HERE.parent.parent.parent  # .../proto75, holds the overlay's own app/ package
sys.path.insert(0, str(OVERLAY))

from app.providers import openalex, semantic_scholar  # noqa: E402

BERT_DOI = "10.18653/v1/n19-1423"
UNKNOWN_DOI = "10.9999/not-in-s2"
BERT_OPENALEX_ID = "W2963341956"

# Only the keys the providers' callers would read (mirrors backend/tests/fixtures/discovery/record.py's S2_PAPER).
S2_PAPER = {
    "paperId": None, "title": None, "year": None, "venue": None, "authors": {"name": None}, "externalIds": None,
    "openAccessPdf": {"url": None}, "citationCount": None,
}  # fmt: skip
WORK = {
    "id": None, "doi": None, "title": None, "publication_year": None, "cited_by_count": None,
    "authorships": {"author": {"display_name": None}},
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


def trim_page(body: dict) -> dict:
    """Keeps offset/next and trims each item's citedPaper/citingPaper record."""
    trimmed = {"offset": body["offset"], "data": []}
    if "next" in body:
        trimmed["next"] = body["next"]
    for item in body["data"]:
        inner_key = "citedPaper" if "citedPaper" in item else "citingPaper"
        trimmed["data"].append({inner_key: trim(item[inner_key], S2_PAPER)})
    return trimmed


async def record_s2() -> None:
    fields = semantic_scholar.PAPER_FIELDS
    async with semantic_scholar.new_client("") as s2:
        # limit=40 splits BERT's 63 references into two real pages: one with `next`, one the tail.
        page1 = await s2_get(s2, f"/graph/v1/paper/DOI:{BERT_DOI}/references", fields=fields, limit=40, offset=0)
        page1 = page1.raise_for_status().json()
        save("s2_references_bert_page1", trim_page(page1))
        page2 = await s2_get(
            s2, f"/graph/v1/paper/DOI:{BERT_DOI}/references", fields=fields, limit=40, offset=page1["next"]
        )
        save("s2_references_bert_page2", trim_page(page2.raise_for_status().json()))

        citations = await s2_get(s2, f"/graph/v1/paper/DOI:{BERT_DOI}/citations", fields=fields, limit=5, offset=0)
        save("s2_citations_bert_page1", trim_page(citations.raise_for_status().json()))

        unknown = await s2_get(s2, f"/graph/v1/paper/DOI:{UNKNOWN_DOI}/references", fields=fields)
        save("s2_references_unknown", {"status": unknown.status_code, "body": unknown.json()})


async def record_openalex(mailto: str) -> None:
    async with openalex.new_client(mailto) as oa:
        work = await oa.get(f"/works/{BERT_OPENALEX_ID}", params={"select": "referenced_works"})
        body = work.raise_for_status().json()
        save("openalex_referenced_works_bert", {"referenced_works": body["referenced_works"]})
        first_two = "|".join(short.rsplit("/", 1)[-1] for short in body["referenced_works"][:2])

        batch = await oa.get("/works", params={"filter": f"openalex_id:{first_two}", "select": openalex.WORK_FIELDS})
        save("openalex_works_by_ids_batch", {"results": trim(batch.raise_for_status().json()["results"], WORK)})

        citing = await oa.get(
            "/works",
            params={
                "filter": f"cites:{BERT_OPENALEX_ID}",
                "sort": "publication_date:desc",
                "per-page": 5,
                "select": openalex.WORK_FIELDS,
            },
        )
        save("openalex_citing_works_page", {"results": trim(citing.raise_for_status().json()["results"], WORK)})


async def main() -> None:
    mailto = sys.argv[1] if len(sys.argv) > 1 else None
    await record_s2()
    await asyncio.sleep(1)
    await record_openalex(mailto)


if __name__ == "__main__":
    asyncio.run(main())
