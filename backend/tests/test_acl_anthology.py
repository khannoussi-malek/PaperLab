"""ACL Anthology: a weekly harvest of its public BibTeX dump, searched locally (M32 batch 7). No network in
these tests: httpx.MockTransport answers the dump request, and tests/fixtures/acl_anthology_sample.bib.gz stands in
for the real ~47 MB file (eleven entries of mixed types, LaTeX escapes, one with no URL, some with no DOI or abstract).
"""

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core import paper_sources
from app.core.candidates import from_acl_anthology
from app.core.source_registry import BY_ID
from app.models import ExternalRef
from app.models.harvest import HarvestCursor
from app.providers import acl_anthology
from app.workers import harvest

pytestmark = pytest.mark.anyio

FIXTURE = Path(__file__).parent / "fixtures" / "acl_anthology_sample.bib.gz"
STORED_IDS = {
    "2023.acl-long.1", "2022.emnlp-main.5", "2021.tacl-1.3", "P18-1001",
    "2020.fixture-main.7", "2024.naacl-short.2", "2019.acl-demos.4", "Q18-1009",
}  # fmt: skip
NEVER_STORED = {"2023.acl-long", "2023.book-1", "2017.nothing"}  # the proceedings, the book, and the entry with no URL
ETAG = '"fixture-etag-1"'
LAST_MODIFIED = "Thu, 12 Nov 2026 03:00:00 GMT"
_real_new_client = acl_anthology.new_client


def _by_id() -> dict[str, dict]:
    return {entry["id"]: entry for entry in acl_anthology.iter_entries(FIXTURE)}


class FakeDump:
    """Answers the dump URL from a MockTransport and records every request it receives."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200

    def respond(self, status: int) -> None:
        self.status = status

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, content=FIXTURE.read_bytes(), headers={"ETag": ETAG, "Last-Modified": LAST_MODIFIED})


@pytest.fixture
def dump(monkeypatch) -> FakeDump:
    fake = FakeDump()
    transport = httpx.MockTransport(fake.handle)
    monkeypatch.setattr(acl_anthology, "new_client", lambda **_: _real_new_client(transport=transport))
    return fake


def _use_test_session(monkeypatch, session, module):
    @asynccontextmanager
    async def reuse():
        yield session  # never closes it: the `session` fixture's own teardown does that

    monkeypatch.setattr(module, "SessionLocal", reuse)


async def _acl_rows(session) -> list[ExternalRef]:
    query = select(ExternalRef).where(ExternalRef.external_ids.has_key("acl_anthology"))
    return list((await session.execute(query)).scalars().all())


def _ids(rows) -> set[str]:
    return {row.external_ids["acl_anthology"] for row in rows}


# --- provider: parsing and mapping (no database) ---


def test_only_articles_and_conference_papers_are_kept_and_named_by_their_url_id():
    ids = {entry["id"] for entry in acl_anthology.iter_entries(FIXTURE)}
    assert ids == STORED_IDS
    assert ids.isdisjoint(NEVER_STORED)


def test_latex_escapes_are_decoded_to_unicode():
    by_id = _by_id()
    assert by_id["2023.acl-long.1"]["title"] == "Žilka: Learning BERT for Fixtures"
    assert by_id["2023.acl-long.1"]["authors"] == ["Jan Novák", "Ada Doe"]
    assert by_id["P18-1001"]["title"] == "Ranges 1–5 in Old Style Entries"
    assert by_id["P18-1001"]["abstract"] == "Öld entries keep working."


def test_the_citation_key_is_ignored_and_the_id_comes_from_the_url():
    by_id = _by_id()
    assert by_id["2020.fixture-main.7"]["title"] == "Transformers for Fixtures Revisited"
    assert "key-not-the-id" not in by_id


def test_a_missing_doi_or_abstract_maps_to_none():
    candidate = from_acl_anthology(_by_id()["2022.emnlp-main.5"])
    assert candidate.doi is None
    assert candidate.abstract is None
    assert candidate.external_ids == {"acl_anthology": "2022.emnlp-main.5"}


@pytest.mark.parametrize("acl_id", ["2023.acl-long.1", "P18-1001", "2021.tacl-1.3"])
def test_the_pdf_url_follows_the_anthology_convention(acl_id):
    candidate = from_acl_anthology(_by_id()[acl_id])
    assert candidate.pdf_urls == [f"https://aclanthology.org/{acl_id}.pdf"]


def test_the_mapper_keeps_doi_venue_year_and_authors():
    candidate = from_acl_anthology(_by_id()["2023.acl-long.1"])
    assert candidate.doi == "10.18653/v1/2023.acl-long.1"
    assert candidate.year == 2023
    assert candidate.venue.startswith("Proceedings of the 61st")
    assert candidate.authors == ["Jan Novák", "Ada Doe"]
    assert candidate.sources == ("acl_anthology",)


# --- provider: the download (no database) ---


async def test_download_writes_the_body_and_returns_its_validators(tmp_path, dump):
    client = acl_anthology.new_client()
    target = tmp_path / "dump.bib.gz"
    try:
        validators = await acl_anthology.download(client, target, etag=None, last_modified=None)
    finally:
        await client.aclose()

    assert target.read_bytes() == FIXTURE.read_bytes()
    assert validators == acl_anthology.Download(etag=ETAG, last_modified=LAST_MODIFIED)


async def test_download_sends_the_stored_validators_and_returns_none_on_304(tmp_path, dump):
    dump.respond(304)
    client = acl_anthology.new_client()
    try:
        validators = await acl_anthology.download(
            client, tmp_path / "dump.bib.gz", etag=ETAG, last_modified=LAST_MODIFIED
        )
    finally:
        await client.aclose()

    assert validators is None
    sent = dump.requests[0].headers
    assert sent["if-none-match"] == ETAG
    assert sent["if-modified-since"] == LAST_MODIFIED


async def test_download_sends_no_email_no_key_and_no_query(tmp_path, dump):
    client = acl_anthology.new_client()
    try:
        await acl_anthology.download(client, tmp_path / "dump.bib.gz", etag=None, last_modified=None)
    finally:
        await client.aclose()

    [request] = dump.requests
    assert request.url.path == "/anthology+abstracts.bib.gz"
    assert request.url.query == b""
    assert "authorization" not in request.headers
    assert all("@" not in value and "mailto" not in value.lower() for value in request.headers.values())


async def test_download_errors_raise_without_the_request_url(tmp_path, dump):
    dump.respond(500)
    client = acl_anthology.new_client()
    try:
        with pytest.raises(httpx.HTTPStatusError) as raised:
            await acl_anthology.download(client, tmp_path / "dump.bib.gz", etag=None, last_modified=None)
    finally:
        await client.aclose()

    assert "aclanthology.org" not in str(raised.value)


# --- harvest: database ---


async def test_a_200_twice_gives_the_same_rows(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)

    await harvest.harvest_acl_anthology({})
    first = _ids(await _acl_rows(session))
    await harvest.harvest_acl_anthology({})
    second_rows = await _acl_rows(session)

    assert STORED_IDS <= first
    assert _ids(second_rows) == first
    assert len(second_rows) == len(first)
    row = next(r for r in second_rows if r.external_ids["acl_anthology"] == "2023.acl-long.1")
    assert row.doi == "10.18653/v1/2023.acl-long.1"
    assert row.venue.startswith("Proceedings of the 61st")


async def test_a_304_leaves_rows_and_cursor_untouched(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})
    session.expire_all()
    rows_before = len(await _acl_rows(session))
    cursor = await session.get(HarvestCursor, "acl_anthology")
    cursor_before = (cursor.etag, cursor.last_modified, cursor.last_synced_at)

    dump.respond(304)
    await harvest.harvest_acl_anthology({})

    session.expire_all()
    assert len(await _acl_rows(session)) == rows_before
    cursor = await session.get(HarvestCursor, "acl_anthology")
    assert (cursor.etag, cursor.last_modified, cursor.last_synced_at) == cursor_before
    assert dump.requests[-1].headers["if-none-match"] == ETAG


async def test_a_failed_download_leaves_the_cursor_alone(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})
    session.expire_all()
    cursor = await session.get(HarvestCursor, "acl_anthology")
    cursor_before = (cursor.etag, cursor.last_synced_at)

    dump.respond(503)
    with pytest.raises(httpx.HTTPStatusError):
        await harvest.harvest_acl_anthology({})

    session.expire_all()
    cursor = await session.get(HarvestCursor, "acl_anthology")
    assert (cursor.etag, cursor.last_synced_at) == cursor_before


async def test_proceedings_books_and_url_less_entries_are_never_stored(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})

    assert _ids(await _acl_rows(session)).isdisjoint(NEVER_STORED)


# --- Workspace Search: local, ACL rows only ---


async def _harvested_search(session, monkeypatch, term: str) -> set[str]:
    _use_test_session(monkeypatch, session, acl_anthology)
    entries, _ = await acl_anthology.search_page(None, term, 50, 0)
    return {entry["id"] for entry in entries}


async def test_search_returns_only_acl_rows(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})
    session.add(
        ExternalRef(
            title="Transformer Cryptography", external_ids={"iacr_eprint": "2026/9999"}, sources=["iacr_eprint"]
        )
    )
    await session.flush()

    ids = await _harvested_search(session, monkeypatch, "transformer")

    assert "2023.acl-long.1" in ids
    assert "2026/9999" not in ids
    assert ids <= STORED_IDS


async def test_every_word_must_match(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})

    assert "2024.naacl-short.2" not in await _harvested_search(session, monkeypatch, "transformer fixture")
    assert "2023.acl-long.1" in await _harvested_search(session, monkeypatch, "transformer fixture")
    assert await _harvested_search(session, monkeypatch, "transformer nonexistentword") == set()


async def test_search_is_case_insensitive(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})

    assert "2023.acl-long.1" in await _harvested_search(session, monkeypatch, "TRANSFORMER")


async def test_title_and_abstract_are_both_searched(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    await harvest.harvest_acl_anthology({})

    assert "2021.tacl-1.3" in await _harvested_search(session, monkeypatch, "parsing")  # title only
    assert "Q18-1009" in await _harvested_search(session, monkeypatch, "spelling")  # abstract only


# --- registry and schedule ---


def test_acl_anthology_is_an_on_by_default_keyless_discovery_source():
    spec = BY_ID["acl_anthology"]
    assert spec.enabled_by_default is True
    assert spec.is_discovery_source is True
    assert spec.keyed is False
    assert spec.page is acl_anthology.search_page
    assert spec.mapper is from_acl_anthology


def test_harvest_acl_anthology_is_registered_as_a_weekly_cron_job():
    from app.workers.settings import WorkerSettings

    [job] = [job for job in WorkerSettings.cron_jobs if job.name == "harvest_acl_anthology"]
    assert job.weekday == "sun"


async def test_the_harvest_downloads_nothing_when_acl_is_off_or_on_a_test_stack(session, dump, monkeypatch):
    _use_test_session(monkeypatch, session, harvest)
    calls = []

    async def no_download(*args, **kwargs):
        calls.append(1)
        return None

    monkeypatch.setattr(harvest.acl_anthology, "download", no_download)
    await paper_sources.update(session, {"enabled": {"acl_anthology": False}})
    await harvest.harvest_acl_anthology({})
    assert calls == []  # turned off in Settings: no download at all

    await paper_sources.update(session, {"enabled": {"acl_anthology": True}})
    monkeypatch.setattr(harvest.settings, "discovery_provider", "fake")
    await harvest.harvest_acl_anthology({})
    assert calls == []  # the test stack's fake providers never reach the real site


def test_authors_split_on_and_across_a_line_break():
    assert acl_anthology._authors("Smith, Ann and\n  Jones, Bo") == [
        acl_anthology._author("Smith, Ann"),
        acl_anthology._author("Jones, Bo"),
    ]
