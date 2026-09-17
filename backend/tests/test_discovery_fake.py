import pytest
from sqlalchemy import delete

from app.core import discovery, references
from app.core.errors import Conflict
from app.core.paper_sources import SOURCES, SourceSettings
from app.models import Paper, paper_references
from app.providers import discovery_fake
from app.providers.extraction import extract

# Fetches and embeds take one advisory lock (core/references.py); in a test it lasts until the rollback, so these
# files share one xdist worker, or two of them deadlock on the same stored reference.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]


@pytest.fixture
async def fake_providers(session):
    # An E2E run killed mid-test can leave the fake's papers in the shared dev database (D15); hide them here.
    await session.execute(delete(Paper).where(Paper.doi.like(f"{discovery_fake.DOI_PREFIX}%")))
    every_source = SourceSettings(contact_email=discovery_fake.MAILTO, enabled=dict.fromkeys(SOURCES, True))
    providers = discovery.build_providers(every_source, discovery_fake.transport())
    yield providers
    await providers.aclose()


async def test_the_e2e_fake_finds_three_papers_and_suggests_the_same_three(session, fake_providers):
    found = await discovery.search(session, fake_providers, "anything")
    suggested = await discovery.similar(session, fake_providers, Paper(title="A reader's paper", file_path="/x.pdf"))

    titles = [discovery_fake.FREE_TITLE, discovery_fake.LANDING_TITLE, discovery_fake.CLOSED_TITLE]
    assert ([c.title for c in found.results], found.notices) == (titles, [])
    assert [c.title for c in suggested] == titles
    assert [c.sources for c in found.results] == [
        ("openalex", "crossref", "arxiv", "core"), ("openalex", "crossref"), ("openalex", "crossref")
    ]  # fmt: skip
    assert [bool(c.pdf_urls) for c in found.results] == [True, True, False]


async def test_with_openalex_off_as_on_the_e2e_stack_the_badges_are_m19s(session):
    defaults = SourceSettings(contact_email=discovery_fake.MAILTO)
    providers = discovery.build_providers(defaults, discovery_fake.transport())

    found = await discovery.search(session, providers, "anything")
    await providers.aclose()

    assert [c.sources for c in found.results] == [("crossref", "arxiv", "core"), ("crossref",), ("crossref",)]
    assert [bool(c.pdf_urls) for c in found.results] == [True, True, False]  # the landing page's link from Unpaywall


async def test_the_e2e_fakes_free_paper_downloads_a_pdf_extraction_can_title(session, fake_providers, pdf_dir):
    [free, landing, _] = (await discovery.search(session, fake_providers, "anything")).results

    paper = await discovery.add(session, fake_providers, free, pdf_dir)

    assert extract(paper.file_path).title == discovery_fake.FREE_TITLE
    with pytest.raises(Conflict, match="No free PDF was found"):
        await discovery.add(session, fake_providers, landing, pdf_dir)


async def test_the_e2e_fake_answers_identifier_lookups_with_its_free_paper(session, fake_providers):
    by_doi = await discovery.search(session, fake_providers, "10.5555/anything")
    by_arxiv = await discovery.search(session, fake_providers, "2401.00001")

    assert [c.title for c in by_doi.results] == [c.title for c in by_arxiv.results] == [discovery_fake.FREE_TITLE]


async def test_the_e2e_fake_gives_any_paper_three_references_and_one_citing_work(session, fake_providers):
    await session.execute(delete(paper_references))  # the owner's links would change nothing here, but stay out
    reader = Paper(title="A reader's paper", file_path="/x.pdf")
    session.add(reader)
    await session.flush()

    notices = await references.fetch(session, fake_providers, reader)

    cites = await references.listing(session, reader.id, "cites")
    cited_by = await references.listing(session, reader.id, "cited_by")
    assert notices == []
    assert sorted(r.title for r in cites.rows) == sorted(
        [discovery_fake.FREE_TITLE, discovery_fake.LANDING_TITLE, discovery_fake.CLOSED_TITLE]
    )
    assert [r.title for r in cited_by.rows] == [discovery_fake.FREE_TITLE]
    assert {r.title: r.has_pdf for r in cites.rows}[discovery_fake.CLOSED_TITLE] is False
