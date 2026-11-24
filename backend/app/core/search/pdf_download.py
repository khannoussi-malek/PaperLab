"""Downloading one PDF from a link: follow a landing page to the file, refuse bot checks and oversize files."""

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from app.core.papers import papers, pdf_links
from app.core.platform.redact import redact
from app.domain.errors import InvalidInput

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 100 * 1024 * 1024


BOT_CHECK_STATUSES = (403, 429, 503)
CHALLENGE_MARKERS = (b"Just a moment", b"challenge-platform")


async def _is_bot_check(response: httpx.Response) -> bool:
    """A Cloudflare challenge: its `cf-mitigated` header, or its interstitial page. Recognised, never answered."""
    if response.status_code not in BOT_CHECK_STATUSES:
        return False
    if "cf-mitigated" in response.headers:
        return True
    if "cloudflare" not in response.headers.get("server", "").lower():
        return False
    async for chunk in response.aiter_bytes():  # the first chunk holds the page's title
        return any(marker in chunk for marker in CHALLENGE_MARKERS)
    return False


MAX_LANDING_BYTES = 2 * 1024 * 1024
PDF_USER_AGENT = "PaperLab (+https://github.com/khannoussi-malek/PaperLab)"  # names the tool; never imitates a browser
FOLLOWED = "not_a_pdf → followed citation_pdf_url"


class _PdfMeta(HTMLParser):
    """The first `<meta name="citation_pdf_url" content=…>`, its attributes in either order."""

    def __init__(self):
        super().__init__()
        self.url: str | None = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if self.url is None and tag == "meta" and (fields.get("name") or "").lower() == "citation_pdf_url":
            self.url = (fields.get("content") or "").strip() or None


def _declared_pdf(page: str, base: str) -> str | None:
    parser = _PdfMeta()
    parser.feed(page)
    return urljoin(base, parser.url) if parser.url else None


async def _fetch_pdf(http: httpx.AsyncClient, url: str) -> tuple[bytes | None, str, str | None]:
    """(the PDF or None, why, the page's declared PDF URL or None): why is `pdf`, `http_<status>`, `bot_check`,
    `too_large` or `not_a_pdf`. Only a not_a_pdf page under MAX_LANDING_BYTES can declare a PDF."""
    async with http.stream("GET", url) as response:
        if response.status_code != 200:
            outcome = "bot_check" if await _is_bot_check(response) else f"http_{response.status_code}"
            logger.info("no PDF at %s: %s", redact(url), outcome)
            return None, outcome, None
        final_url = str(response.url)
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > MAX_PDF_BYTES:
                logger.info("no PDF at %s: over %d bytes", redact(url), MAX_PDF_BYTES)
                return None, "too_large", None
    if not body.startswith(papers.PDF_MAGIC):
        logger.info("no PDF at %s: the body is not a PDF", redact(url))
        declared = None
        if len(body) < MAX_LANDING_BYTES:
            declared = _declared_pdf(body.decode("utf-8", errors="replace"), final_url)
        return None, "not_a_pdf", declared
    return bytes(body), "pdf", None


async def _try(http: httpx.AsyncClient, url: str, check: bool = False) -> tuple[bytes | None, str, str | None]:
    try:
        if check:  # a URL a publisher page declared is not the caller's own link: never fetch a private address
            await pdf_links.check_url(url)
        return await _fetch_pdf(http, url)
    except InvalidInput as exc:
        if str(exc) != "unsafe_url":
            raise
        return None, "unsafe_url", None
    except httpx.HTTPError as exc:
        logger.info("no PDF at %s: %s", redact(url), redact(str(exc)))
        return None, f"error: {type(exc).__name__}", None


async def download_pdf(http: httpx.AsyncClient, urls: list[str]) -> tuple[bytes | None, list[dict[str, str]]]:
    """(the first body that is a PDF, what each URL tried said), in order. A failing URL moves on to the next; a page
    that declares its PDF (citation_pdf_url) gets that one URL tried too, and a followed page is not followed again.
    The URLs in `tried` have their query secrets hidden."""
    tried: list[dict[str, str]] = []
    for url in urls:
        data, outcome, declared = await _try(http, url)
        tried.append({"url": redact(url), "outcome": FOLLOWED if declared else outcome})
        if declared:
            # ponytail: one hop; the PDF's own page is not followed
            data, outcome, _ = await _try(http, declared, check=True)
            tried.append({"url": redact(declared), "outcome": outcome})
        if data is not None:
            return data, tried
    return None, tried
