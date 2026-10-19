"""NCBI's PMC Article Datasets on AWS (https://registry.opendata.aws/ncbi-pmc/): a public S3 bucket, no auth, NCBI's
sanctioned bulk channel for the PMC Open Access subset. Each article version is a folder `PMC<n>.<v>/` holding
`PMC<n>.<v>.pdf` when PMC has a PDF for it, beside its JSON, text and XML.

Probed live on 2026-10-19: an S3 ListObjectsV2 by prefix (`?list-type=2&prefix=PMC4512184.`) answers XML naming every
key; a closed paper answers KeyCount 0. Author manuscripts (`is_manuscript: true`, licence TDM) are in the same bucket
as JSON, text and XML only, never a PDF. The bucket receives the PMCID and nothing else: no email, no key. Requests
go through the caller's PDF client (PaperLab's own User-Agent), paced by one module-level pacer.
"""

import re
import xml.etree.ElementTree as ET

import httpx

from app.providers.http import _Pacer

BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
MIN_INTERVAL = 1 / 3  # polite: the bucket has no published limit
_PACER = _Pacer(MIN_INTERVAL)
_S3 = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_PMCID = re.compile(r"(?:PMC)?(\d+)", re.IGNORECASE)


def normalize(pmcid: str | None) -> str | None:
    """The PMCID as "PMC4512184", from "4512184", "pmc4512184" or "PMC4512184"; None for anything else."""
    match = _PMCID.fullmatch((pmcid or "").strip())
    return f"PMC{match[1]}" if match else None


def listing_url(pmcid: str) -> str:
    return f"{BUCKET}/?list-type=2&prefix={pmcid}."


def pdf_key(listing_xml: str, pmcid: str) -> str | None:
    """The highest version's `<pmcid>.<v>/<pmcid>.<v>.pdf` key in a ListBucketResult, or None.
    ponytail: reads the first 1,000 keys only (IsTruncated is ignored); an article with that many version files and
    figures could hide its PDF. List with delimiter=/ and fetch the top version's PDF directly if that ever bites.
    The listing is parsed by ElementTree on expat (>= 2.4 refuses entity expansion bombs; no external entities)."""
    wanted = re.compile(rf"{re.escape(pmcid)}\.(\d+)/{re.escape(pmcid)}\.\1\.pdf")
    keys = [el.text or "" for el in ET.fromstring(listing_xml).iter(f"{_S3}Key")]
    versions = [(int(match[1]), key) for key in keys if (match := wanted.fullmatch(key))]
    return max(versions)[1] if versions else None


async def pdf_url(http: httpx.AsyncClient, pmcid: str) -> tuple[str | None, str]:
    """(the PDF's URL or None, the listing URL asked). Raises httpx.HTTPError when the listing fails."""
    await _PACER.wait_turn()
    response = await http.get(f"{BUCKET}/", params={"list-type": "2", "prefix": f"{pmcid}."})
    response.raise_for_status()
    try:
        key = pdf_key(response.text, pmcid)
    except ET.ParseError as exc:
        raise httpx.DecodingError(f"the PMC bucket's listing isn't XML: {exc}", request=response.request) from exc
    return (f"{BUCKET}/{key}" if key else None), listing_url(pmcid)


async def wait_turn() -> None:
    """The pacer, for the PDF request that follows a listing."""
    await _PACER.wait_turn()
