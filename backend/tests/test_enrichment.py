import httpx
import pytest
from conftest import recorded
from sqlalchemy import select

from app.core import enrichment
from app.core.enrichment import PdfHints
from app.models import Paper, paper_topics

pytestmark = pytest.mark.anyio

BERT_TITLE = "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
BERT_PAGE = f"{BERT_TITLE}\nJacob Devlin Ming-Wei Chang Kenton Lee Kristina Toutanova\nGoogle AI Language\n"
BERT_DOI = "10.18653/v1/n19-1423"
BERT_WORK = f"/works/doi:{BERT_DOI}"
BERT_SEARCH = f"/works?title.search:{BERT_TITLE}"


def hints(doi=None, arxiv_id=None, years=(), text=BERT_PAGE, authors=(), keywords=()) -> PdfHints:
    return PdfHints(
        doi=doi, arxiv_id=arxiv_id, years=frozenset(years), text=text, authors=list(authors), keywords=list(keywords)
    )


async def add_paper(session, **fields) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", **{"title": BERT_TITLE, **fields})
    session.add(paper)
    await session.commit()
    return paper


async def enrich(session, fake, paper, pdf: PdfHints) -> Paper:
    await enrichment.enrich_paper(session, fake.client if fake else None, paper.id, pdf)
    await session.refresh(paper)
    return paper


def works_requests(fake) -> list[str]:
    """Paths of the /works requests; author requests are covered in test_enrichment_authors.py."""
    return [r.url.path for r in fake.requests if r.url.path.startswith("/works")]


async def topics_of(session, paper_id) -> dict[tuple[str, str], float | None]:
    rows = await session.execute(select(paper_topics).where(paper_topics.c.paper_id == paper_id))
    return {(row.source, row.label): row.score for row in rows}


async def test_a_doi_match_fills_the_paper_metadata(session, fake_openalex):
    work = recorded("work_bert")
    fake_openalex.route(BERT_WORK, work)
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session, title="BERT: Pre-training of Deep Bidirectional Transformers for")

    paper = await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI))

    assert (paper.openalex_id, paper.doi, paper.title, paper.year) == ("W2963341956", BERT_DOI, BERT_TITLE, 2019)
    assert (paper.type, paper.is_retracted, paper.oa_status) == ("conference-paper", False, "gold")
    assert paper.venue == work["primary_location"]["raw_source_name"]  # no source record: the raw venue name
    assert paper.oa_url == "https://doi.org/10.18653/v1/n19-1423"
    assert (paper.cited_by_count, paper.referenced_works_count) == (work["cited_by_count"], 52)
    # OpenAlex spells "Ming‐Wei" with U+2010 HYPHEN; the byline keeps its spelling.
    assert paper.authors == [a["author"]["display_name"] for a in work["authorships"]]
    assert paper.authors[0] == "Jacob Devlin"


async def test_a_doi_match_keeps_topics_with_source_and_score(session, fake_openalex):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    # The re-run below finds the paper's now-stored openalex_id first (0 credits), same underlying work.
    fake_openalex.route("/works/W2963341956", recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)

    await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI, keywords=["language models"]))
    await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI, keywords=["language models"]))  # a re-run

    topics = await topics_of(session, paper.id)
    assert topics[("openalex", "Topic Modeling")] == pytest.approx(0.9999, abs=1e-4)
    # "Computer science" is both a keyword and a concept in the response; it is stored once.
    assert topics[("openalex", "Computer science")] == pytest.approx(0.535, abs=1e-3)
    assert topics[("author", "language models")] is None
    assert len(topics) == 10  # 9 distinct OpenAlex labels + 1 author keyword


async def test_a_retracted_work_sets_the_flag_venue_issn_and_oa_location(session, fake_openalex):
    fake_openalex.route("/works/doi:10.1016/j.ijantimicag.2020.105949", recorded("work_retracted"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session, title="Hydroxychloroquine and azithromycin as a treatment of COVID-19")

    paper = await enrich(session, fake_openalex, paper, hints(doi="10.1016/j.ijantimicag.2020.105949"))

    assert paper.is_retracted is True
    assert (paper.venue, paper.issn) == ("International Journal of Antimicrobial Agents", "0924-8579")
    assert (paper.oa_status, paper.oa_url) == ("green", "https://www.ncbi.nlm.nih.gov/pmc/articles/7102549")
    assert paper.abstract is None  # OpenAlex withholds this publisher's abstracts


def test_the_abstract_is_rebuilt_from_the_inverted_index():
    assert enrichment.abstract_text({"world": [1, 3], "hello": [0], "again": [2]}) == "hello world again world"
    assert enrichment.abstract_text(None) is None


async def test_an_arxiv_id_is_tried_as_a_doi_before_title_search(session, fake_openalex):
    fake_openalex.route("/works/doi:10.48550/arxiv.2210.12440", recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)

    paper = await enrich(session, fake_openalex, paper, hints(arxiv_id="2210.12440", years={2022}))

    assert paper.openalex_id == "W2963341956"
    assert works_requests(fake_openalex) == ["/works/doi:10.48550/arxiv.2210.12440"]


async def test_title_search_accepts_a_hit_whose_year_and_first_author_agree(session, fake_openalex):
    # BERT's arXiv DOI is merged into the NAACL record, so OpenAlex answers 404 for it; ruling 2 requires the
    # explicit route rather than relying on FakeOpenAlex's (removed) default reply.
    fake_openalex.route("/works/doi:10.48550/arxiv.1810.04805", httpx.Response(404))
    fake_openalex.route(BERT_SEARCH, recorded("search_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)

    # The arXiv PDF says 2018; OpenAlex dates the merged NAACL record 2019. One year apart still agrees.
    paper = await enrich(session, fake_openalex, paper, hints(arxiv_id="1810.04805", years={2018}))

    assert paper.openalex_id == "W2963341956"
    # BERT's arXiv DOI is merged into the NAACL record, so OpenAlex answers 404 for it and title search runs.
    assert works_requests(fake_openalex) == ["/works/doi:10.48550/arxiv.1810.04805", "/works"]


async def test_title_search_skips_a_hit_whose_first_author_is_not_on_the_page(session, fake_openalex):
    results = recorded("search_bert")
    # The decoy first: a 2020 Japanese article whose title mentions Jacob Devlin, first author 柴田 知秀.
    fake_openalex.route(BERT_SEARCH, {**results, "results": results["results"][::-1]})
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)

    paper = await enrich(session, fake_openalex, paper, hints(years={2020}))

    assert paper.openalex_id == "W2963341956"


@pytest.mark.parametrize(
    "pdf",
    [hints(years={2015}), hints(years={2018}, text="a page without the first author's name")],
    ids=["year disagrees", "first author disagrees"],
)
async def test_title_search_rejects_a_hit_that_disagrees(session, fake_openalex, pdf):
    fake_openalex.route(BERT_SEARCH, recorded("search_bert"))
    paper = await add_paper(session)

    paper = await enrich(session, fake_openalex, paper, pdf)

    assert (paper.openalex_id, paper.year, paper.authors) == (None, None, [])


def test_a_first_author_matches_across_accents_case_and_unicode_hyphens():
    work = {"publication_year": 2020, "authorships": [{"author": {"display_name": "Anne Chabrière‐Smith"}}]}

    assert enrichment.is_confirmed_match(work, hints(years={2020}, text="ANNE CHABRIERE-SMITH, Aix-Marseille"))
    assert not enrichment.is_confirmed_match(work, hints(years={2020}, text="Anne Chabrière-Smithson"))


async def test_without_a_year_to_check_no_title_search_is_spent(session, fake_openalex):
    paper = await add_paper(session)

    await enrich(session, fake_openalex, paper, hints())

    assert fake_openalex.requests == []


async def test_no_match_falls_back_to_the_pdf_metadata(session, fake_openalex):
    fake_openalex.route(BERT_SEARCH, recorded("search_no_match"))
    paper = await add_paper(session)

    pdf = hints(years={2019}, authors=["Ada Lovelace"], keywords=["engines"])

    paper = await enrich(session, fake_openalex, paper, pdf)

    assert (paper.openalex_id, paper.authors) == (None, ["Ada Lovelace"])
    assert await topics_of(session, paper.id) == {("author", "engines"): None}


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("OpenAlex unreachable"),
        httpx.ReadTimeout("OpenAlex timed out"),
        httpx.Response(429, headers={"retry-after": "1"}, json={"error": "Rate limit exceeded"}),
        httpx.Response(500),
    ],
    ids=["network error", "timeout", "rate limited", "server error"],
)
async def test_openalex_failures_fall_back_to_the_pdf_metadata(session, fake_openalex, failure):
    fake_openalex.route(BERT_WORK, failure)
    paper = await add_paper(session)

    paper = await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI, authors=["Ada Lovelace"]))

    assert (paper.openalex_id, paper.authors) == (None, ["Ada Lovelace"])


async def test_without_a_client_only_the_pdf_metadata_is_used(session, fake_openalex):
    # M1: the fallback now also writes hints.doi, a recorded DOI, so this needs fake_openalex's isolation too.
    paper = await add_paper(session)

    paper = await enrich(session, None, paper, hints(doi=BERT_DOI, authors=["Ada Lovelace"]))

    assert (paper.openalex_id, paper.authors) == (None, ["Ada Lovelace"])


async def test_a_matched_paper_keeps_its_data_while_openalex_is_down(session, fake_openalex):
    fake_openalex.route("/works/W2963341956", httpx.ConnectError("OpenAlex unreachable"))
    paper = await add_paper(session, openalex_id="W2963341956", doi=BERT_DOI, authors=["Jacob Devlin"])

    paper = await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI, authors=["Someone Else"]))

    assert (paper.openalex_id, paper.authors) == ("W2963341956", ["Jacob Devlin"])
    assert works_requests(fake_openalex) == ["/works/W2963341956"]  # the stored ID is tried first


async def test_corrected_fields_are_never_overwritten(session, fake_openalex):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session, title="My Title", is_retracted=True, manual_fields=["title", "is_retracted"])

    paper = await enrich(session, fake_openalex, paper, hints(doi=BERT_DOI))

    assert (paper.title, paper.is_retracted, paper.year) == ("My Title", True, 2019)


async def test_a_duplicate_pdf_printed_doi_keeps_the_second_papers_authors_and_topics(session):
    # M1's fallback writes doi and authors in one UPDATE. A second paper with the same PDF-printed DOI must not
    # lose its byline and keyword topics to the papers.doi UNIQUE constraint.
    paper1 = await add_paper(session)
    paper2 = await add_paper(session)
    pdf = hints(doi="10.1000/xyz-duplicate", authors=["Ada Lovelace"], keywords=["engines"])

    paper1 = await enrich(session, None, paper1, pdf)
    paper2 = await enrich(session, None, paper2, pdf)

    assert paper1.doi == "10.1000/xyz-duplicate"  # the first paper still gets it
    assert (paper2.doi, paper2.authors) == (None, ["Ada Lovelace"])
    assert await topics_of(session, paper2.id) == {("author", "engines"): None}


async def test_a_title_search_match_keeps_the_stored_doi_when_the_work_has_none(session, fake_openalex):
    fallback_doi = "10.1000/fallback-only"
    paper = await add_paper(session)
    paper = await enrich(session, None, paper, hints(doi=fallback_doi))
    assert paper.doi == fallback_doi

    # The stored DOI is tried first (404: no such work), so the search below still runs.
    fake_openalex.route(f"/works/doi:{fallback_doi}", httpx.Response(404))
    fake_openalex.route(BERT_SEARCH, {"results": [{**recorded("work_bert"), "doi": None}]})
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py

    paper = await enrich(session, fake_openalex, paper, hints(years={2019}))

    assert paper.doi == fallback_doi  # the match's null doi never overwrites it
    assert paper.openalex_id == "W2963341956"  # the rest of the match still applies


async def test_a_trusted_id_match_with_no_authorships_keeps_the_stored_byline(session, fake_openalex):
    fake_openalex.route("/works/W2963341956", {**recorded("work_bert"), "authorships": []})
    paper = await add_paper(session, openalex_id="W2963341956", authors=["Jacob Devlin"])

    paper = await enrich(session, fake_openalex, paper, hints())

    assert paper.authors == ["Jacob Devlin"]


async def test_a_duplicate_openalex_match_keeps_the_second_papers_metadata_and_topics(session, fake_openalex):
    # Symmetric with the doi case: two papers matching the same work must not raise on papers.openalex_id UNIQUE.
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper1 = await add_paper(session)
    paper2 = await add_paper(session)

    paper1 = await enrich(session, fake_openalex, paper1, hints(doi=BERT_DOI))
    paper2 = await enrich(session, fake_openalex, paper2, hints(doi=BERT_DOI))

    assert paper1.openalex_id == "W2963341956"
    assert (paper2.openalex_id, paper2.doi) == (None, None)  # dropped: another paper already holds them
    assert paper2.title == BERT_TITLE  # the rest of the match still applies
    assert paper2.authors == paper1.authors
    topics = await topics_of(session, paper2.id)
    assert topics[("openalex", "Topic Modeling")] == pytest.approx(0.9999, abs=1e-4)
