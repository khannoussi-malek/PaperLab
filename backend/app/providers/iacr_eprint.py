"""IACR Cryptology ePrint Archive, harvested via OAI-PMH (https://eprint.iacr.org/oai). Network failures,
timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed live on 2026-10-10: no free-text search exists at all (the architecture doc's own prior research,
confirmed unchanged) -- the only API is OAI-PMH metadata harvesting. A ListRecords call with
metadataPrefix=oai_dc and a from/until date range (YYYY-MM-DD) returns real oai_dc records; a page with
more than ~500 matches ends in a <resumptionToken>...</resumptionToken> (confirmed live: a 9-month range
gave completeListSize=3121, cursor=500) -- the NEXT page is a separate request with ONLY
verb=ListRecords&resumptionToken=<token>, no other params (the date range is encoded inside the opaque
token itself, standard OAI-PMH convention). A deleted/withdrawn record is signaled by <header
status="deleted"> with no <metadata> body at all (confirmed live, present in a real recent date range) --
skipped here rather than crashing on the missing metadata; acting on the deletion signal is a later
milestone's job, not this module's. Identify confirmed deletedRecord="persistent" (deletions are always
signaled, never silently dropped) and earliestDatestamp 1996-01-01. No key, no documented rate limit.
"""

from xml.etree import ElementTree

import httpx

BASE_URL = "https://eprint.iacr.org"
TIMEOUT = httpx.Timeout(30.0)  # a full ListRecords page can be a few hundred KB; generous on purpose.

_NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/"}


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # IACR's OAI-PMH endpoint takes neither a contact email nor a key; both parameters exist only to
    # satisfy the uniform new_client(*, email=None, api_key=None, transport=None) signature every
    # provider shares.
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=transport)


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL -- same convention
    every provider in this codebase follows."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"IACR ePrint answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


def _text(record_elem: ElementTree.Element, tag: str) -> list[str]:
    return [el.text for el in record_elem.findall(f".//dc:{tag}", _NS) if el.text]


def _parse_page(xml_text: str) -> tuple[list[dict], str | None]:
    root = ElementTree.fromstring(xml_text)
    entries: list[dict] = []
    for record in root.findall(".//oai:record", _NS):
        header = record.find("oai:header", _NS)
        if header.get("status") == "deleted":
            continue  # acting on this signal is a later milestone's job, not this one's
        identifier = header.findtext("oai:identifier", namespaces=_NS)
        datestamp = header.findtext("oai:datestamp", namespaces=_NS)
        metadata = record.find("oai:metadata", _NS)
        creators = _text(metadata, "creator")
        descriptions = _text(metadata, "description")
        entries.append(
            {
                "identifier": identifier,
                "datestamp": datestamp,
                "title": next(iter(_text(metadata, "title")), None),
                "creators": creators,
                "description": next(iter(descriptions), None),
            }
        )
    token_elem = root.find(".//oai:resumptionToken", _NS)
    token = token_elem.text if token_elem is not None and token_elem.text else None
    return entries, token


async def fetch_page(
    http: httpx.AsyncClient,
    *,
    from_date: str | None = None,
    until_date: str | None = None,
    resumption_token: str | None = None,
) -> tuple[list[dict], str | None]:
    """One OAI-PMH page. Pass `resumption_token` alone to continue a prior page (OAI-PMH's own
    convention: the date range is encoded inside the opaque token itself, so no other param is sent
    alongside it). Pass `from_date`/`until_date` alone to start a fresh range. Returns (entries,
    next_resumption_token_or_None)."""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        if from_date:
            params["from"] = from_date
        if until_date:
            params["until"] = until_date
    response = await http.get("/oai", params=params)
    return _parse_page(_checked(response).text)
