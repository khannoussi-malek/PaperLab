import copy

import httpx
import pytest
from conftest import recorded
from sqlalchemy import func, insert, select, text, update

from app.core import enrichment
from app.core.enrichment import PdfHints
from app.models import Author, Paper, paper_authors

pytestmark = pytest.mark.anyio

BERT_DOI = "10.18653/v1/n19-1423"
BERT_AUTHOR_IDS = ["A5057457287", "A5076904467", "A5081862885", "A5053947885"]


async def enrich_with(session, fake, work: dict, doi: str = BERT_DOI) -> Paper:
    """Enriches a new paper whose PDF prints `doi`, with OpenAlex answering `work` for it.

    Finding 3: a hinted DOI must pass the first-author check, so the fake page text always carries `work`'s own
    first author -- these tests are about authorship linking, not about the match-confirmation rule.
    """
    fake.route(f"/works/doi:{doi}", work)
    paper = Paper(title="placeholder", file_path="/nonexistent.pdf")
    session.add(paper)
    await session.commit()
    authorships = work.get("authorships") or []
    first_author = authorships[0]["author"]["display_name"] if authorships else ""
    hints = PdfHints(doi=doi, arxiv_id=None, years=frozenset(), text=first_author, authors=[], keywords=[])
    await enrichment.enrich_paper(session, fake.client, paper.id, hints)
    return paper


async def authorships_of(session, paper_id) -> list[tuple]:
    """(openalex_id, display_name, position, is_corresponding, institution) in author order."""
    link = paper_authors.c
    rows = await session.execute(
        select(Author.openalex_id, Author.display_name, link.position, link.is_corresponding, link.institution)
        .join(paper_authors, link.author_id == Author.id)
        .where(link.paper_id == paper_id)
        .order_by(link.position)
    )
    return [tuple(row) for row in rows]


async def count_authors(session, *where) -> int:
    return await session.scalar(select(func.count()).select_from(Author).where(*where))


async def test_authors_are_keyed_by_openalex_id_in_author_order(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})  # author details are covered below
    paper = await enrich_with(session, fake_openalex, recorded("work_bert"))

    rows = await authorships_of(session, paper.id)
    assert [(r[0], r[2]) for r in rows] == [(oid, n) for n, oid in enumerate(BERT_AUTHOR_IDS, start=1)]
    assert rows[0] == ("A5057457287", "Jacob Devlin", 1, False, None)
    chang = await session.scalar(select(Author).where(Author.openalex_id == "A5076904467"))
    assert chang.orcid == "0000-0002-0137-8895"


async def test_institution_at_publication_and_corresponding_flag_sit_on_the_join(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})  # author details are covered above
    work = recorded("work_retracted")
    paper = await enrich_with(session, fake_openalex, work, doi="10.1016/j.ijantimicag.2020.105949")

    rows = await authorships_of(session, paper.id)
    assert len(rows) == 18
    assert rows[0][1:] == ("Philippe Gautret", 1, False, "Aix-Marseille Université")
    assert rows[-1][1:] == ("Didier Raoult", 18, True, "Aix-Marseille Université")


async def test_two_authors_with_the_same_name_but_different_ids_stay_two_rows(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})  # author details are covered above
    work = copy.deepcopy(recorded("work_bert"))
    work["authorships"][1]["author"]["display_name"] = "Jacob Devlin"

    await enrich_with(session, fake_openalex, work)

    assert await count_authors(session, Author.display_name == "Jacob Devlin") == 2


async def test_one_author_on_two_papers_is_one_row(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})  # author details are covered above
    other = copy.deepcopy(recorded("work_bert"))
    other.update(id="https://openalex.org/W1", doi="https://doi.org/10.1000/other")

    first = await enrich_with(session, fake_openalex, recorded("work_bert"))
    second = await enrich_with(session, fake_openalex, other, doi="10.1000/other")

    assert await count_authors(session, Author.openalex_id == "A5057457287") == 1
    assert [r[0] for r in await authorships_of(session, first.id)] == BERT_AUTHOR_IDS
    assert [r[0] for r in await authorships_of(session, second.id)] == BERT_AUTHOR_IDS


async def test_an_author_listed_twice_on_a_work_keeps_the_first_position(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})  # author details are covered above
    work = copy.deepcopy(recorded("work_bert"))
    work["authorships"][2]["author"] = dict(work["authorships"][0]["author"])

    paper = await enrich_with(session, fake_openalex, work)

    positions = [(r[0], r[2]) for r in await authorships_of(session, paper.id)]
    assert positions == [("A5057457287", 1), ("A5076904467", 2), ("A5053947885", 4)]


async def test_author_details_come_from_one_batched_request(session, fake_openalex):
    fake_openalex.route("/authors", recorded("authors_bert"))

    await enrich_with(session, fake_openalex, recorded("work_bert"))

    [batch] = [r for r in fake_openalex.requests if r.url.path == "/authors"]
    assert batch.url.params["filter"] == "openalex_id:" + "|".join(BERT_AUTHOR_IDS)
    assert batch.url.params["per-page"] == "50"
    devlin = await session.scalar(select(Author).where(Author.openalex_id == "A5057457287"))
    assert (devlin.works_count, devlin.h_index, devlin.last_institution) == (50, 23, None)
    assert "Devlin, Jacob" in devlin.alt_names and devlin.fetched_at is not None
    chang = await session.scalar(select(Author).where(Author.openalex_id == "A5076904467"))
    assert (chang.h_index, chang.last_institution) == (59, "University of Ulster")
    assert chang.topics[0] == {"label": "Topic Modeling", "count": 87}


async def test_authors_fetched_under_30_days_ago_are_not_refetched_but_older_ones_are(session, fake_openalex):
    fake_openalex.route("/authors", {"results": []})
    fetched = {"A5057457287": "29 days", "A5076904467": "31 days"}
    await session.execute(insert(Author), [{"openalex_id": oid, "display_name": oid} for oid in fetched])
    for oid, age in fetched.items():
        ago = func.now() - text(f"interval '{age}'")
        await session.execute(update(Author).where(Author.openalex_id == oid).values(fetched_at=ago))
    await session.commit()

    await enrich_with(session, fake_openalex, recorded("work_bert"))

    [batch] = [r for r in fake_openalex.requests if r.url.path == "/authors"]
    assert batch.url.params["filter"] == "openalex_id:A5076904467|A5081862885|A5053947885"


async def test_a_second_enrichment_right_after_makes_no_author_request(session, fake_openalex):
    fake_openalex.route("/authors", recorded("authors_bert"))
    await enrich_with(session, fake_openalex, recorded("work_bert"))
    assert "/authors" in [r.url.path for r in fake_openalex.requests]
    fake_openalex.requests.clear()

    same_authors = recorded("work_bert") | {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.1000/copy"}
    await enrich_with(session, fake_openalex, same_authors, doi="10.1000/copy")

    assert [r.url.path for r in fake_openalex.requests] == ["/works/doi:10.1000/copy"]


async def test_a_failed_author_fetch_keeps_the_paper_and_its_authorships(session, fake_openalex):
    fake_openalex.route("/authors", httpx.ConnectError("OpenAlex unreachable"))

    paper = await enrich_with(session, fake_openalex, recorded("work_bert"))

    await session.refresh(paper)
    assert paper.openalex_id == "W2963341956"
    assert len(await authorships_of(session, paper.id)) == 4
    assert await count_authors(session, Author.openalex_id.in_(BERT_AUTHOR_IDS), Author.fetched_at.is_not(None)) == 0


async def test_an_authorship_without_an_openalex_id_creates_no_author(session, fake_openalex):
    work = copy.deepcopy(recorded("work_bert"))
    for authorship in work["authorships"]:
        authorship["author"]["id"] = None

    paper = await enrich_with(session, fake_openalex, work)

    await session.refresh(paper)
    assert await authorships_of(session, paper.id) == []
    assert paper.authors[0] == "Jacob Devlin"  # the byline still names them
