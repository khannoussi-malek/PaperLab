import uuid

import pytest
from sqlalchemy import update

from app.core import enrichment
from app.models import Paper
from app.scripts import backfill_biblio
from tests.test_enrichment import add_paper, hints
from tests.test_source_enrichment import fake_crossref

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

DOI = "10.9999/m40.biblio"
BIBLIO = ("volume", "issue", "pages", "editors", "pmid", "pmcid")
CROSSREF = {
    "type": "journal-article",
    "volume": "12",
    "issue": "3",
    "page": "45-67",
    "editor": [{"given": "Ada", "family": "Lovelace"}, {"name": "The Committee"}],
}


async def test_crossref_fills_volume_issue_pages_and_editors(session):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref(CROSSREF)
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    assert (paper.volume, paper.issue, paper.pages) == ("12", "3", "45-67")
    assert paper.editors == ["Ada Lovelace", "The Committee"]


async def test_enrichment_never_overwrites_manual_fields(session):
    paper = await add_paper(session, doi=DOI, volume="99", manual_fields=["volume"])
    client, _ = fake_crossref(CROSSREF)
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    assert (paper.volume, paper.issue) == ("99", "3")


def openalex_work(**extra):
    return {
        "id": "https://openalex.org/W9990040",
        "doi": f"https://doi.org/{DOI}",
        "title": "Biblio test",
        "biblio": {"volume": "7", "issue": None, "first_page": "10", "last_page": "20"},
        "ids": {
            "pmid": "https://pubmed.ncbi.nlm.nih.gov/12345",
            "pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC678",
        },
        **extra,
    }


def test_openalex_work_gives_biblio_and_bare_ids():
    fields = enrichment.work_fields(openalex_work())
    assert (fields["volume"], fields["issue"], fields["pages"]) == ("7", None, "10-20")
    assert (fields["pmid"], fields["pmcid"]) == ("12345", "PMC678")
    bare = enrichment.work_fields({"id": "https://openalex.org/W1"})
    assert (bare["volume"], bare["pages"], bare["pmid"], bare["pmcid"]) == (None, None, None, None)


async def test_backfill_fills_nulls_only_and_is_idempotent(session):
    kept = await add_paper(session, doi="10.9999/m40.kept", volume="1", issue="2")
    locked = await add_paper(session, doi="10.9999/m40.locked", pages="x", manual_fields=["pages"])
    fresh = await add_paper(session, doi="10.9999/m40.fresh")
    ids = [kept.id, locked.id, fresh.id]
    client, _ = fake_crossref(CROSSREF)
    first = await backfill_biblio.run(session, client, None, delay=0, only=ids)
    for paper in (kept, locked, fresh):
        await session.refresh(paper)
    assert (kept.volume, kept.issue, kept.pages) == ("1", "2", "45-67")
    assert locked.pages == "x" and locked.volume == "12"
    assert (fresh.volume, fresh.editors) == ("12", ["Ada Lovelace", "The Committee"])
    second = await backfill_biblio.run(session, client, None, delay=0, only=ids)
    assert first["updated"] == 3 and second["updated"] == 0


async def test_backfill_survives_a_crossref_error(session):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref(None, 500)
    summary = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id])
    assert summary["updated"] == 0


async def test_the_api_exposes_the_six_fields(client, session):
    created = (await client.post("/api/papers", files={"file": ("p.pdf", b"%PDF-1.7\nbody", "application/pdf")})).json()
    assert {k: created[k] for k in BIBLIO} == dict.fromkeys(BIBLIO)
    values = {"volume": "1", "issue": "2", "pages": "3-4", "editors": ["A B"], "pmid": "5", "pmcid": "PMC6"}
    await session.execute(update(Paper).where(Paper.id == uuid.UUID(created["id"])).values(**values))
    body = (await client.get(f"/api/papers/{created['id']}")).json()
    assert {k: body[k] for k in BIBLIO} == values
