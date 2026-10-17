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
    fields = enrichment.openalex_biblio(openalex_work())
    assert (fields["volume"], fields["issue"], fields["pages"]) == ("7", None, "10-20")
    assert (fields["pmid"], fields["pmcid"]) == ("12345", "PMC678")
    bare = enrichment.openalex_biblio({"id": "https://openalex.org/W1"})
    assert (bare["volume"], bare["pages"], bare["pmid"], bare["pmcid"]) == (None, None, None, None)
    one_page = enrichment.openalex_biblio(openalex_work(biblio={"first_page": "10", "last_page": "10"}))
    assert one_page["pages"] == "10"


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


async def test_openalex_re_enrichment_never_overwrites_a_held_value(session, fake_openalex):
    fake_openalex.route(
        f"/works/doi:{DOI}", openalex_work(biblio={"volume": "8", "first_page": "45", "last_page": "68"})
    )
    fake_openalex.route("/authors", {"results": []})
    paper = await add_paper(session, doi=DOI, pages="45-67", manual_fields=["doi"])
    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints())
    await session.refresh(paper)
    assert (paper.pages, paper.volume, paper.pmid) == ("45-67", "8", "12345")


async def test_one_enrichment_makes_one_crossref_request(session):
    paper = await add_paper(session, doi=DOI)
    client, seen = fake_crossref(CROSSREF)
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    assert [r.url.path for r in seen] == [f"/works/{DOI}"]


async def test_nothing_left_to_learn_asks_nobody(session):
    paper = await add_paper(session, doi=DOI, source_type="book", volume="1", issue="2", pages="3", editors=["A"])
    client, seen = fake_crossref(CROSSREF)
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    assert seen == []


async def test_backfill_ignores_papers_missing_only_editors(session):
    paper = await add_paper(session, doi=DOI, volume="1", issue="2", pages="3", pmid="4", pmcid="PMC5")
    client, seen = fake_crossref(CROSSREF)
    summary = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id])
    assert summary["checked"] == 0 and seen == []


async def test_the_backfill_sends_openalex_its_api_key(monkeypatch):
    # Keyless, a library-wide run hits OpenAlex's anonymous limits and PubMed ids quietly stay empty.
    from contextlib import asynccontextmanager  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from app.scripts import backfill_biblio  # noqa: PLC0415

    built = {}

    class Client:
        async def aclose(self):
            pass

    def openalex_client(**kwargs):
        built.update(kwargs)
        return Client()

    async def sources(_session):
        return SimpleNamespace(
            contact_email="me@example.org", enabled={"crossref": False, "openalex": True}, api_keys={"openalex": "k-1"}
        )

    @asynccontextmanager
    async def fake_session():
        yield None

    async def run(_session, _cr, _oa):
        return {}

    monkeypatch.setattr(backfill_biblio, "SessionLocal", fake_session)
    monkeypatch.setattr(backfill_biblio.paper_sources, "get", sources)
    monkeypatch.setattr(backfill_biblio.openalex, "new_client", openalex_client)
    monkeypatch.setattr(backfill_biblio, "run", run)

    await backfill_biblio.main()

    assert built == {"email": "me@example.org", "api_key": "k-1"}


def test_the_backfill_help_prints_and_runs_nothing(monkeypatch, capsys):
    # A `--help` once started the real run on the live library: arguments are parsed before anything else.
    from app.scripts import backfill_biblio  # noqa: PLC0415

    monkeypatch.setattr(backfill_biblio, "main", lambda dry_run: pytest.fail("ran instead of printing help"))
    with pytest.raises(SystemExit) as exited:
        backfill_biblio.cli(["--help"])
    assert exited.value.code == 0 and "--dry-run" in capsys.readouterr().out


async def test_a_dry_run_counts_the_papers_it_would_ask_about_and_asks_nobody(session, monkeypatch, capsys):
    from contextlib import asynccontextmanager  # noqa: PLC0415

    from app.scripts import backfill_biblio  # noqa: PLC0415

    paper = Paper(file_path="/nonexistent.pdf", title="dry run", doi=f"10.5555/dry-{uuid.uuid4().hex[:8]}")
    session.add(paper)
    await session.flush()

    @asynccontextmanager
    async def this_session():
        yield session

    monkeypatch.setattr(backfill_biblio, "SessionLocal", this_session)
    monkeypatch.setattr(backfill_biblio.crossref, "new_client", lambda **k: pytest.fail("built a client"))
    monkeypatch.setattr(backfill_biblio.openalex, "new_client", lambda **k: pytest.fail("built a client"))

    await backfill_biblio.main(dry_run=True)

    assert "would check" in capsys.readouterr().out
