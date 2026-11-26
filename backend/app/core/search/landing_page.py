"""A paper's page on a publisher's site, read for what identifies it. Most publishers put the DOI in the page's
`<meta>` tags for indexers (Highwire's `citation_doi`, Dublin Core's `dc.identifier`, PRISM's `prism.doi`), some an
arXiv ID or just the title: so a link whose URL holds no DOI (a Nature article page, IEEE Xplore, ScienceDirect)
can still be looked up by what its page says.

Only http(s) pages on public hosts are read, through the client PaperLab already uses for publisher sites, with a
time limit and a size cap: the page is the owner's own link, but a link is still outside input."""

import asyncio
import html
import re

import httpx

from app.core.papers.pdf_links import check_url
from app.domain.errors import DomainError

# The head of a page holds its meta tags; the rest is never needed. A slow site gets READ_SECONDS for the whole read.
MAX_BYTES = 1_500_000
TIMEOUT = httpx.Timeout(10.0)
READ_SECONDS = 15.0

COULD_NOT_READ = "Couldn't read that page ({why}). Copy the paper's DOI or title from it instead."
TURNED_AWAY = "That site turns automatic readers away. Copy the paper's DOI or title from the page instead."
SAYS_NOTHING = "That page doesn't say which paper it is. Copy the paper's DOI or title from it instead."

_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
# Bounded, so a page of unclosed tags can't make the scan quadratic.
_META = re.compile(r"<meta\b[^>]{0,4000}>", re.IGNORECASE)
_ATTR = re.compile(r"""([a-z_:.-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_CHARSET = re.compile(rb"""<meta[^>]{0,200}charset\s*=\s*["']?([a-z0-9_-]+)""", re.IGNORECASE)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)")
# Meta names, in the order they're trusted. Only the scholarly ones: a site's own `og:title` ("Nature", "Editorial")
# would find some other paper.
_DOI_NAMES = ("citation_doi", "prism.doi", "dc.identifier", "dc.identifier.doi", "bepress_citation_doi")
_ARXIV_NAMES = ("citation_arxiv_id",)
_TITLE_NAMES = ("citation_title", "dc.title")


# Publishers whose article links spell their DOI's suffix, so the page needn't be read (Nature, for one, answers an
# automatic reader with a bot check).
_DOI_IN_LINK = (
    (re.compile(r"^https?://(?:www\.)?nature\.com/articles/([a-z0-9][a-z0-9.\-]+)", re.IGNORECASE), "10.1038/{}"),
)
# The page a bot check shows instead of the article (Cloudflare, Akamai and their like).
_BOT_CHECK = re.compile(
    r"<title>\s*(?:client challenge|just a moment|attention required|access denied|are you a robot)", re.IGNORECASE
)


def doi_from_link(url: str) -> str | None:
    """The DOI a publisher's article link spells, without reading the page."""
    for pattern, doi in _DOI_IN_LINK:
        if found := pattern.match(url.strip()):
            return doi.format(found.group(1).rstrip("."))
    return None


def is_bot_check(page: str) -> bool:
    return bool(_BOT_CHECK.search(page[:20_000]))


class PageUnreadable(Exception):
    """The page couldn't be read: its sentence says why, for the owner."""


def is_link(query: str) -> bool:
    return bool(_URL.match(query.strip()))


def meta_tags(page: str) -> dict[str, str]:
    """The page's meta tags, by lowercase name (or property): the first of each name wins."""
    found: dict[str, str] = {}
    for tag in _META.findall(page):
        attrs = {k.lower(): v.strip("\"'") for k, v in _ATTR.findall(tag)}
        name = (attrs.get("name") or attrs.get("property") or "").lower()
        if name and "content" in attrs:
            found.setdefault(name, html.unescape(attrs["content"]).strip())
    return found


def identify(page: str) -> str | None:
    """What to search for this page: its DOI, else `arXiv:<id>`, else its title; None when it says none of these."""
    tags = meta_tags(page)
    for name in _DOI_NAMES:
        if (doi := _DOI.search(tags.get(name, ""))) is not None:
            return doi.group(1).rstrip(".,;)")
    for name in _ARXIV_NAMES:
        if arxiv_id := tags.get(name):
            return f"arXiv:{arxiv_id}"
    for name in _TITLE_NAMES:
        if title := tags.get(name):
            return " ".join(title.split())
    return None


async def read(http: httpx.AsyncClient, url: str) -> str:
    """The page's first MAX_BYTES as text. Raises PageUnreadable with the reason in words. The URL is checked as a PDF
    link is (http(s), every address public); the client's own guard checks each redirect hop the same way."""
    try:
        await check_url(url)
        async with asyncio.timeout(READ_SECONDS):
            return await _fetch(http, url)
    except DomainError as exc:  # unsafe_url, from the check or the client's guard
        raise PageUnreadable(COULD_NOT_READ.format(why="only public web pages are read")) from exc
    except TimeoutError as exc:
        raise PageUnreadable(COULD_NOT_READ.format(why="the site took too long")) from exc
    except httpx.HTTPError as exc:
        raise PageUnreadable(COULD_NOT_READ.format(why="the site didn't answer")) from exc


async def _fetch(http: httpx.AsyncClient, url: str) -> str:
    async with http.stream("GET", url, timeout=TIMEOUT, headers={"Accept": "text/html"}) as response:
        if response.status_code >= 400:
            raise PageUnreadable(COULD_NOT_READ.format(why=f"the site answered {response.status_code}"))
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) >= MAX_BYTES:
                break
        return _decode(bytes(body[:MAX_BYTES]), response.charset_encoding)


def _decode(body: bytes, header_charset: str | None) -> str:
    """The header's charset, else the page's own `<meta charset>`, else UTF-8."""
    named = _CHARSET.search(body[:4096])
    for charset in (header_charset, named and named.group(1).decode("ascii")):
        if not charset:
            continue
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            continue  # a charset Python doesn't know
    return body.decode("utf-8", errors="replace")
