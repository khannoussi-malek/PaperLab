import httpx
import pytest

from app.core import enrichment
from app.providers import crossref
from app.scripts import backfill_source_types
from tests.test_enrichment import add_paper, hints

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

DOI = "10.9999/f6.test"


def fake_crossref(work=None, status=200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, text="nope")
        return httpx.Response(200, json={"message": work})

    return crossref.new_client(email="me@example.org", transport=httpx.MockTransport(handler)), seen


async def enrich(session, paper, client):
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    return paper


async def test_crossref_type_and_published_version_fill_the_paper(session):
    paper = await add_paper(session, doi=DOI)
    client, seen = fake_crossref({"type": "posted-content", "relation": {"is-preprint-of": [{"id": "10.1234/PUB"}]}})
    await enrich(session, paper, client)
    assert (paper.source_type, paper.peer_reviewed, paper.published_doi) == ("preprint", "false", "10.1234/pub")
    assert seen[0].url.params["mailto"] == "me@example.org"


async def test_a_messy_doi_is_normalised_before_the_call(session):
    paper = await add_paper(session, doi="https://doi.org/10.9999/F6.UPPER")
    client, seen = fake_crossref({"type": "journal-article"})
    await enrich(session, paper, client)
    assert paper.source_type == "journal_article" and seen[0].url.path == "/works/10.9999/f6.upper"


@pytest.mark.parametrize("status", [404, 429, 500])
async def test_crossref_failure_leaves_fields_and_does_not_raise(session, status):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref(None, status)
    await enrich(session, paper, client)
    assert (paper.source_type, paper.peer_reviewed) == (None, "unknown")


async def test_crossref_network_error_is_tolerated(session):
    def boom(request):
        raise httpx.ConnectError("down")

    paper = await add_paper(session, doi=DOI)
    await enrich(session, paper, crossref.new_client(transport=httpx.MockTransport(boom)))
    assert paper.source_type is None


async def test_an_owner_edit_survives_enrichment(session):
    paper = await add_paper(
        session,
        doi=DOI,
        source_type="magazine",
        peer_reviewed="unknown",
        manual_fields=["source_type", "peer_reviewed"],
    )
    client, _ = fake_crossref({"type": "journal-article"})
    await enrich(session, paper, client)
    assert (paper.source_type, paper.peer_reviewed) == ("magazine", "unknown")


async def test_a_locked_source_type_leaves_peer_review_alone(session):
    paper = await add_paper(session, doi=DOI, source_type="book", manual_fields=["source_type"])
    await enrich(session, paper, fake_crossref({"type": "journal-article"})[0])
    assert (paper.source_type, paper.peer_reviewed) == ("book", "unknown")


async def test_an_arxiv_doi_is_a_preprint_without_asking_crossref(session):
    paper = await add_paper(session, doi="10.48550/arxiv.1706.03762")
    client, seen = fake_crossref({"type": "journal-article"})
    await enrich(session, paper, client)
    assert (paper.source_type, paper.peer_reviewed, seen) == ("preprint", "false", [])


async def test_a_known_source_type_is_not_asked_again(session):
    paper = await add_paper(session, doi=DOI, source_type="book")
    client, seen = fake_crossref({"type": "journal-article"})
    await enrich(session, paper, client)
    assert paper.source_type == "book"
    assert [r.url.path for r in seen] == [
        f"/works/{DOI}"
    ]  # the one fetch is for volume/issue; the type is not re-derived


async def test_backfill_maps_from_type_or_crossref_skips_manual_and_is_idempotent(session):
    by_type = await add_paper(session, type="conference-paper", doi="10.9999/bf.1")
    by_crossref = await add_paper(session, doi="10.9999/bf.2")
    locked = await add_paper(session, doi="10.9999/bf.3", source_type="magazine", manual_fields=["source_type"])
    client, seen = fake_crossref({"type": "book-chapter"})
    ids = [by_type.id, by_crossref.id, locked.id]

    first = await backfill_source_types.run(session, client, delay=0, only=ids)
    second = await backfill_source_types.run(session, client, delay=0, only=ids)

    for paper in (by_type, by_crossref, locked):
        await session.refresh(paper)
    assert [p.source_type for p in (by_type, by_crossref, locked)] == ["proceedings", "chapter", "magazine"]
    assert first["updated"] == 2 and second["updated"] == 0
    assert len(seen) == 1  # only by_crossref ever asked, and the second run found it done


def raw_crossref(body):
    return crossref.new_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))


@pytest.mark.parametrize(
    "body", [{}, {"status": "ok"}, {"message": {"type": "posted-content", "relation": ["x"]}}, {"message": []}]
)
async def test_an_odd_crossref_reply_leaves_fields_and_does_not_raise(session, body):
    paper = await add_paper(session, doi=DOI)
    await enrich(session, paper, raw_crossref(body))
    assert (paper.source_type, paper.published_doi) == (None, None)


async def test_published_doi_is_recorded_even_when_the_source_type_is_locked(session):
    paper = await add_paper(session, doi=DOI, source_type=None, manual_fields=["source_type"])
    client, _ = fake_crossref({"type": "posted-content", "relation": {"is-preprint-of": [{"id": "10.1234/pub"}]}})
    await enrich(session, paper, client)
    assert (paper.source_type, paper.published_doi) == (None, "10.1234/pub")


ANDERSON_WORK = {
    "type": "proceedings-article",
    "author": [
        {"given": "Barrett R.", "family": "Anderson"},
        {"given": "Jash Hemant", "family": "Shah"},
        {"given": "Max", "family": "Kreminski"},
    ],
    "issued": {"date-parts": [[2024, 6, 23]]},
    "container-title": ["Creativity and Cognition"],
}
ANDERSON_PAGE = "Homogenization Effects of Large Language Models on Human Creative Ideation\nBARRETT R. ANDERSON\n"


async def enrich_upload(session, paper, page, years=(2024,), work=ANDERSON_WORK):
    client, _ = fake_crossref(work)
    await enrichment.enrich_paper(session, None, paper.id, hints(text=page, years=years), crossref_http=client)
    await session.refresh(paper)
    return paper


async def test_without_openalex_crossref_fills_an_uploads_authors_year_and_venue(session):
    paper = await enrich_upload(session, await add_paper(session, doi=DOI), ANDERSON_PAGE)
    assert paper.authors == ["Barrett R. Anderson", "Jash Hemant Shah", "Max Kreminski"]
    assert (paper.year, paper.venue, paper.source_type) == (2024, "Creativity and Cognition", "proceedings")
    assert paper.field_sources["bibliographic"] == "crossref"


async def test_crossref_fills_nothing_when_its_first_author_is_not_on_page_one(session):
    page = "Some other paper\nJane Doe\n"  # the DOI on page 1 was a cited paper's
    paper = await enrich_upload(session, await add_paper(session, doi=DOI), page)
    assert (paper.authors, paper.year, paper.venue) == ([], None, None)


async def test_crossref_never_overwrites_an_uploads_known_authors_or_year(session):
    paper = await add_paper(session, doi=DOI, authors=["A. Anderson"], year=2023)
    paper = await enrich_upload(session, paper, ANDERSON_PAGE)
    assert (paper.authors, paper.year, paper.venue) == (["A. Anderson"], 2023, "Creativity and Cognition")


HE_WORK = {
    "type": "journal-article",
    "title": ["Deep Residual Learning for Image Recognition"],
    "author": [{"given": "Kaiming", "family": "He"}],
    "issued": {"date-parts": [[2016]]},
    "container-title": ["CVPR"],
}


async def test_a_short_surname_on_a_page_that_cites_the_doi_fills_nothing_without_a_year_or_title_match(session):
    page = "Our model\nAnn Lee\nWe build on He et al. [3], doi:10.9999/f6.test\n"  # cites He 2016; this is 2023
    paper = await enrich_upload(session, await add_paper(session, doi=DOI), page, years=(2023,), work=HE_WORK)
    assert (paper.authors, paper.year, paper.venue) == ([], None, None)


async def test_a_matching_title_fills_without_a_year_hint(session):
    paper = await add_paper(session, doi=DOI, title="Deep residual learning for image recognition")
    paper = await enrich_upload(session, paper, "Kaiming He\n", years=(), work=HE_WORK)
    assert (paper.authors, paper.year) == (["Kaiming He"], 2016)
