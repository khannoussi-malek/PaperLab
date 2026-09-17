import pytest
from sqlalchemy import delete

from app.core import discovery
from app.core.errors import Conflict
from app.core.paper_sources import SOURCES, SourceSettings
from app.models import Paper
from app.providers import discovery_fake
from app.providers.extraction import extract

pytestmark = pytest.mark.anyio


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
