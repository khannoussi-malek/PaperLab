"""Re-records the OpenAlex responses the tests serve, through the real provider. Needs the network; the test suite
never runs it. Numbers in the tests (h-index, scores, counts) come from the 2026-09-13 recording and will drift.

    cd backend && uv run python -m tests.fixtures.openalex.record you@example.com
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from app.providers import openalex

HERE = Path(__file__).parent
BERT_TITLE = "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
BERT_AUTHOR_IDS = ["A5057457287", "A5076904467", "A5081862885", "A5053947885"]

# Only the keys enrichment reads. None keeps a value whole; a dict keeps those keys (in each item, for lists).
LABEL = {"display_name": None, "score": None}
WORK = {
    "id": None, "doi": None, "title": None, "publication_year": None, "type": None, "is_retracted": None,
    "open_access": {"oa_status": None},
    "best_oa_location": {"pdf_url": None, "landing_page_url": None},
    "primary_location": {"raw_source_name": None, "source": {"display_name": None, "issn_l": None}},
    "cited_by_count": None, "referenced_works_count": None,
    "authorships": {
        "author": {"id": None, "display_name": None, "orcid": None},
        "is_corresponding": None,
        "institutions": {"display_name": None},
    },
    "topics": LABEL, "keywords": LABEL, "concepts": LABEL, "abstract_inverted_index": None,
}  # fmt: skip
AUTHOR = {
    "id": None, "orcid": None, "display_name": None, "display_name_alternatives": None, "works_count": None,
    "cited_by_count": None, "summary_stats": {"h_index": None}, "last_known_institutions": {"display_name": None},
    "topics": {"display_name": None, "count": None},
}  # fmt: skip


def trim(value, shape):
    if shape is None or value is None:
        return value
    if isinstance(value, list):
        return [trim(item, shape) for item in value]
    return {key: trim(value[key], inner) for key, inner in shape.items() if key in value}


def write(name: str, body: dict) -> None:
    """One top-level key, or one result, per line: small enough to read, still diffable."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(", ", ": "))  # noqa: E731
    if "results" in body:
        text = '{"results": [\n' + ",\n".join(compact(r) for r in body["results"]) + "\n]}"
    else:
        text = "{\n" + ",\n".join(f"{json.dumps(k)}: {compact(v)}" for k, v in body.items()) + "\n}"
    (HERE / f"{name}.json").write_text(text + "\n")


async def main(mailto: str) -> None:
    async with openalex.new_client(mailto) as http:
        write("work_bert", trim(await openalex.get_work(http, "doi:10.18653/v1/n19-1423"), WORK))
        write("work_retracted", trim(await openalex.get_work(http, "doi:10.1016/j.ijantimicag.2020.105949"), WORK))
        write("search_bert", {"results": trim(await openalex.search_works(http, BERT_TITLE), WORK)})
        write("search_no_match", {"results": trim(await openalex.search_works(http, "PaperLab E2E Fixture"), WORK)})
        write("authors_bert", {"results": trim(await openalex.get_authors(http, BERT_AUTHOR_IDS), AUTHOR)})


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1]))
    except httpx.HTTPError as exc:
        sys.exit(f"OpenAlex failed: {exc!r}")
