"""A paper's page on a publisher's site, read for what identifies it. Most publishers put the DOI in the page's
`<meta>` tags for indexers (Highwire's `citation_doi`, Dublin Core's `dc.identifier`, PRISM's `prism.doi`), some an
arXiv ID or just the title: so a link whose URL holds no DOI (a Nature article page, IEEE Xplore, ScienceDirect)
can still be looked up by what its page says.

Only http(s) pages on public hosts are read, through the client PaperLab already uses for publisher sites, with a
time limit and a size cap: the page is the owner's own link, but a link is still outside input."""

import html
import ipaddress
import re
from urllib.parse import urlsplit

import httpx

# The head of a page holds its meta tags; the rest is never needed.
MAX_BYTES = 1_500_000
TIMEOUT = httpx.Timeout(10.0)

COULD_NOT_READ = "Couldn't read that page ({why}). Copy the paper's DOI or title from it instead."
SAYS_NOTHING = "That page doesn't say which paper it is. Copy the paper's DOI or title from it instead."

_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([a-z_:.-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)")
# Meta names, in the order they're trusted.
_DOI_NAMES = ("citation_doi", "prism.doi", "dc.identifier", "dc.identifier.doi", "bepress_citation_doi")
_ARXIV_NAMES = ("citation_arxiv_id",)
_TITLE_NAMES = ("citation_title", "dc.title", "og:title")


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


def _public(url: str) -> bool:
    """An http(s) URL whose host isn't this machine or a private network (by name or by literal address)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme not in ("http", "https")
        or not host
        or host == "localhost"
        or host.endswith((".local", ".internal"))
    ):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True  # a name: public hosts are what links name
    return address.is_global


async def read(http: httpx.AsyncClient, url: str) -> str:
    """The page's first MAX_BYTES as text. Raises PageUnreadable with the reason in words."""
    if not _public(url):
        raise PageUnreadable(COULD_NOT_READ.format(why="only public web pages are read"))
    try:
        async with http.stream("GET", url, timeout=TIMEOUT, headers={"Accept": "text/html"}) as response:
            if response.status_code >= 400:
                raise PageUnreadable(COULD_NOT_READ.format(why=f"the site answered {response.status_code}"))
            if not _public(str(response.url)):
                raise PageUnreadable(COULD_NOT_READ.format(why="it redirects off the public web"))
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) >= MAX_BYTES:
                    break
            return body[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise PageUnreadable(COULD_NOT_READ.format(why="the site didn't answer")) from exc
