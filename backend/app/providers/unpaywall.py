"""Unpaywall over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed on 2026-09-17: every request needs an `email` (without one, or with an example.com address other than the
documented unpaywall_01@example.com, it answers 422). An unknown DOI answers 404 with an HTML body.
"""

from urllib.parse import quote

import httpx

from app.providers.openalex import json_body

BASE_URL = "https://api.unpaywall.org"
TIMEOUT = httpx.Timeout(10.0)


def new_client(email: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, params={"email": email}, timeout=TIMEOUT, transport=transport)


# ponytail: no retry on 429, as in openalex.py.


async def pdf_urls(http: httpx.AsyncClient, doi: str) -> list[str]:
    """Free PDF links for `doi`, best location first, without repeats. [] when Unpaywall knows none."""
    response = await http.get(f"/v2/{quote(doi, safe='/:')}")
    if response.status_code == 404:
        return []
    record = json_body(response.raise_for_status())
    # url_for_pdf is null for a location that is only a landing page.
    places = [record.get("best_oa_location"), *(record.get("oa_locations") or [])]
    urls = (place.get("url_for_pdf") for place in places if place)
    return list(dict.fromkeys(url for url in urls if url and url.startswith(("http://", "https://"))))
