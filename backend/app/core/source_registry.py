"""Every paper source PaperLab knows about, in one place: its identity, whether it takes a key, its default
on/off state, how to build its httpx client, and how Find Papers/Similar (`ask`) and Workspace Search
(`page`/`mapper`) each use it (Phase 0). Adding a new source means adding one SourceSpec here — not hand-editing
paper_sources.py, the paper_sources/workspace_search schemas, discovery.py's ASKS, and workspace_search.py's
PAGE_FUNCS/MAPPERS separately, which is exactly the shotgun-surgery pattern that once let a source be present in
one dict and missing from another (the C1 bug).

REGISTRY's own tuple order is D73's merge trust order — most trusted first — preserved byte-for-byte from today's
app.core.paper_sources.SOURCES. Every derived constant below keeps that order.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.candidates import Candidate, from_arxiv, from_core, from_crossref, from_pubmed, from_s2, from_work
from app.providers import arxiv, core_ac, crossref, openalex, pubmed, semantic_scholar, unpaywall

# How many results Find Papers/Similar asks each source for, per query (was discovery.py's PER_SOURCE).
PER_SOURCE = 10

Ask = Callable[[httpx.AsyncClient, str, str], Awaitable[list[Candidate]]]
PageFunc = Callable[[httpx.AsyncClient, str, int, int], Awaitable[tuple[list[Any], int | None]]]
Mapper = Callable[[Any], Candidate | None]
NewClient = Callable[..., httpx.AsyncClient]


async def _openalex(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    if kind == "title":
        return [from_work(w) for w in await openalex.search_works(http, value, per_page=PER_SOURCE)]
    work = await openalex.get_work(http, f"doi:{value}" if kind == "doi" else value)
    return [from_work(work)] if work else []


async def _crossref(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    items = (
        await crossref.search(http, value, PER_SOURCE) if kind == "title" else [await crossref.get_work(http, value)]
    )
    return [candidate for item in items if item and (candidate := from_crossref(item))]


async def _semantic_scholar(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    # OpenAlex's arXiv location filter returned a wrongly merged record for BERT; Semantic Scholar's lookup didn't.
    paper = await semantic_scholar.get_paper(http, f"arXiv:{value}")
    return [from_s2(paper)] if paper else []


async def _arxiv(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    entries = await arxiv.search(http, value, PER_SOURCE) if kind == "title" else [await arxiv.get(http, value)]
    return [from_arxiv(entry) for entry in entries if entry]


async def _core(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    return [from_core(work) for work in await core_ac.search(http, value, PER_SOURCE)]


async def _pubmed(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    return [from_pubmed(entry) for entry in await pubmed.search(http, value, PER_SOURCE)]


@dataclass(frozen=True)
class SourceSpec:
    """One paper source. `ask_kinds` are the classify_query() kinds (app/core/discovery.py) this source answers
    for Find Papers/Similar. `is_discovery_source` is whether it participates in Workspace Search's paginated
    search_batch at all — Unpaywall never does (DOI-only PDF enrichment, applied post-merge, never a search
    source: app/core/paper_sources.py's own comment, "Unpaywall only adds PDF links")."""

    id: str
    name: str
    keyed: bool
    enabled_by_default: bool
    is_discovery_source: bool
    new_client: NewClient
    ask: Ask | None = None
    ask_kinds: tuple[str, ...] = ()
    page: PageFunc | None = None
    mapper: Mapper | None = None
    page_size: int = 20
    starting_cursor: int = 0


REGISTRY: tuple[SourceSpec, ...] = (
    SourceSpec(
        id="openalex", name="OpenAlex", keyed=True, enabled_by_default=False, is_discovery_source=True,
        new_client=openalex.new_client, ask=_openalex, ask_kinds=("title", "doi", "openalex"),
        page=openalex.search_page, mapper=from_work, page_size=100, starting_cursor=1,
    ),
    SourceSpec(
        id="crossref", name="Crossref", keyed=False, enabled_by_default=True, is_discovery_source=True,
        new_client=crossref.new_client, ask=_crossref, ask_kinds=("title", "doi"),
        page=crossref.search_page, mapper=from_crossref, page_size=30,
    ),
    SourceSpec(
        id="semantic_scholar", name="Semantic Scholar", keyed=True, enabled_by_default=True,
        is_discovery_source=True, new_client=semantic_scholar.new_client, ask=_semantic_scholar,
        ask_kinds=("arxiv",), page=semantic_scholar.search_page, mapper=from_s2, page_size=75,
    ),
    SourceSpec(
        id="arxiv", name="arXiv", keyed=False, enabled_by_default=True, is_discovery_source=True,
        new_client=arxiv.new_client, ask=_arxiv, ask_kinds=("title", "arxiv"),
        page=arxiv.search_page, mapper=from_arxiv, page_size=20,
    ),
    SourceSpec(
        id="core", name="CORE", keyed=True, enabled_by_default=True, is_discovery_source=True,
        new_client=core_ac.new_client, ask=_core, ask_kinds=("title",),
        page=core_ac.search_page, mapper=from_core, page_size=20,
    ),
    SourceSpec(
        id="unpaywall", name="Unpaywall", keyed=False, enabled_by_default=True, is_discovery_source=False,
        new_client=unpaywall.new_client,
    ),
    SourceSpec(
        id="pubmed", name="PubMed", keyed=True, enabled_by_default=True, is_discovery_source=True,
        new_client=pubmed.new_client, ask=_pubmed, ask_kinds=("title",),
        page=pubmed.search_page, mapper=from_pubmed, page_size=20,
    ),
)

BY_ID: dict[str, SourceSpec] = {spec.id: spec for spec in REGISTRY}
SOURCE_IDS: tuple[str, ...] = tuple(spec.id for spec in REGISTRY)
DISCOVERY_SOURCE_IDS: tuple[str, ...] = tuple(spec.id for spec in REGISTRY if spec.is_discovery_source)
NAMES: dict[str, str] = {spec.id: spec.name for spec in REGISTRY}
KEYED_IDS: tuple[str, ...] = tuple(spec.id for spec in REGISTRY if spec.keyed)
ENABLED_BY_DEFAULT: dict[str, bool] = {spec.id: spec.enabled_by_default for spec in REGISTRY}
ASKS: dict[str, dict[str, Ask]] = {
    kind: {spec.id: spec.ask for spec in REGISTRY if spec.ask and kind in spec.ask_kinds}
    for kind in ("title", "doi", "arxiv", "openalex")
}
PAGE_SIZE_BY_SOURCE: dict[str, int] = {spec.id: spec.page_size for spec in REGISTRY if spec.is_discovery_source}
PAGE_FUNCS: dict[str, PageFunc] = {spec.id: spec.page for spec in REGISTRY if spec.page}
MAPPERS: dict[str, Mapper] = {spec.id: spec.mapper for spec in REGISTRY if spec.mapper}
STARTING_CURSOR_VALUE: dict[str, int] = {spec.id: spec.starting_cursor for spec in REGISTRY if spec.starting_cursor}
