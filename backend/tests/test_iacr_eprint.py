import httpx
import pytest
from conftest import FakeProvider

from app.providers import iacr_eprint

pytestmark = pytest.mark.anyio

ONE_RECORD_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:eprint.iacr.org:2026/2368</identifier>
        <datestamp>2026-10-05T23:52:42Z</datestamp>
      </header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:identifier>https://eprint.iacr.org/2026/2368</dc:identifier>
          <dc:title>Low-Latency Parallel Digit Decomposition</dc:title>
          <dc:creator>Jung Hee Cheon</dc:creator>
          <dc:creator>Kyungah Cho</dc:creator>
          <dc:description>An overview of digit decomposition.</dc:description>
          <dc:date>2026-10-05T23:52:42Z</dc:date>
          <dc:rights>https://creativecommons.org/licenses/by/4.0/</dc:rights>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>"""

PAGE_WITH_RESUMPTION_TOKEN = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:eprint.iacr.org:2026/0001</identifier>
        <datestamp>2026-01-01T00:00:00Z</datestamp>
      </header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:identifier>https://eprint.iacr.org/2026/0001</dc:identifier>
          <dc:title>Paper One</dc:title>
        </oai_dc:dc>
      </metadata>
    </record>
    <resumptionToken completeListSize="2" cursor="1">abc123token</resumptionToken>
  </ListRecords>
</OAI-PMH>"""

PAGE_WITH_A_DELETED_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record>
      <header status="deleted">
        <identifier>oai:eprint.iacr.org:2020/9999</identifier>
        <datestamp>2026-10-01T00:00:00Z</datestamp>
      </header>
    </record>
    <record>
      <header>
        <identifier>oai:eprint.iacr.org:2026/0002</identifier>
        <datestamp>2026-10-01T00:00:00Z</datestamp>
      </header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:identifier>https://eprint.iacr.org/2026/0002</dc:identifier>
          <dc:title>Paper Two</dc:title>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>"""


@pytest.fixture
async def iacr_api():
    fake = FakeProvider()
    fake.client = iacr_eprint.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_fetch_page_parses_a_single_record(iacr_api):
    iacr_api.reply("/oai", 200, text=ONE_RECORD_PAGE)

    entries, token = await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10")

    assert token is None
    [entry] = entries
    assert entry["identifier"] == "oai:eprint.iacr.org:2026/2368"
    assert entry["title"] == "Low-Latency Parallel Digit Decomposition"
    assert entry["creators"] == ["Jung Hee Cheon", "Kyungah Cho"]
    assert entry["description"] == "An overview of digit decomposition."
    assert entry["datestamp"] == "2026-10-05T23:52:42Z"


async def test_fetch_page_sends_from_and_until_as_query_params(iacr_api):
    iacr_api.reply("/oai", 200, text=ONE_RECORD_PAGE)

    await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10")

    params = iacr_api.requests[0].url.params
    assert params["verb"] == "ListRecords"
    assert params["metadataPrefix"] == "oai_dc"
    assert params["from"] == "2026-10-01"
    assert params["until"] == "2026-10-10"


async def test_fetch_page_returns_the_resumption_token_when_present(iacr_api):
    iacr_api.reply("/oai", 200, text=PAGE_WITH_RESUMPTION_TOKEN)

    entries, token = await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-01-01", until_date="2026-10-10")

    assert len(entries) == 1
    assert token == "abc123token"


async def test_fetch_page_with_a_resumption_token_sends_only_that_param(iacr_api):
    iacr_api.reply("/oai", 200, text=ONE_RECORD_PAGE)

    await iacr_eprint.fetch_page(iacr_api.client, resumption_token="abc123token")

    params = iacr_api.requests[0].url.params
    assert params["verb"] == "ListRecords"
    assert params["resumptionToken"] == "abc123token"
    assert "metadataPrefix" not in params
    assert "from" not in params


async def test_fetch_page_skips_a_deleted_header_without_crashing(iacr_api):
    iacr_api.reply("/oai", 200, text=PAGE_WITH_A_DELETED_RECORD)

    entries, token = await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10")

    assert token is None
    [entry] = entries  # only the non-deleted record
    assert entry["identifier"] == "oai:eprint.iacr.org:2026/0002"


async def test_a_record_with_no_creator_or_description_maps_without_them(iacr_api):
    bare = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record>
      <header><identifier>oai:eprint.iacr.org:2026/0003</identifier><datestamp>2026-10-01T00:00:00Z</datestamp></header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:identifier>https://eprint.iacr.org/2026/0003</dc:identifier>
          <dc:title>Bare</dc:title>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>"""
    iacr_api.reply("/oai", 200, text=bare)

    [entry] = (await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10"))[0]

    assert entry["creators"] == []
    assert entry["description"] is None


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(iacr_api, status, body):
    iacr_api.reply("/oai", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10")


async def test_malformed_xml_in_a_200_response_raises_an_httpx_error(iacr_api):
    iacr_api.reply("/oai", 200, text="<not valid xml")

    with pytest.raises(httpx.HTTPError):
        await iacr_eprint.fetch_page(iacr_api.client, from_date="2026-10-01", until_date="2026-10-10")
