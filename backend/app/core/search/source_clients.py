"""The HTTP clients PaperLab asks each source with, built from the owner's source settings and keys."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.papers import paper_sources, pdf_links
from app.core.papers.paper_sources import SourceSettings
from app.core.search import source_registry
from app.core.search.pdf_download import PDF_USER_AGENT
from app.providers import discovery_fake

PDF_TIMEOUT = httpx.Timeout(10.0, read=30.0)


@dataclass(frozen=True)
class Providers:
    """The clients one request uses. A source that is off, or lacks a key it needs, has none in `clients`; a PDF
    host (arxiv.org, a publisher, a repository, or a redirect target) never agreed to receive the owner's email,
    so `pdf` is separate and always present."""

    pdf: httpx.AsyncClient
    clients: dict[str, httpx.AsyncClient] = field(default_factory=dict)
    # When this Providers last searched arXiv by title (one slot, mutated): a bulk add spaces its searches by it.
    last_search: list[float] = field(default_factory=list, compare=False)

    def client(self, source: str) -> httpx.AsyncClient | None:
        return self.clients.get(source)

    def without(self, *sources: str) -> "Providers":
        """A copy with these sources' clients removed — for tests simulating a source being off."""
        return replace(self, clients={k: v for k, v in self.clients.items() if k not in sources})

    async def aclose(self) -> None:
        await self.pdf.aclose()
        for client in self.clients.values():
            await client.aclose()


def build_providers(sources: SourceSettings, transport: httpx.AsyncBaseTransport | None = None) -> Providers:
    on, email, keys = sources.enabled, sources.contact_email, sources.api_keys
    clients = {
        spec.id: spec.new_client(email=email, api_key=keys.get(spec.key_source or spec.id), transport=transport)
        for spec in source_registry.REGISTRY
        if (sources.unpaywall_on if spec.id == "unpaywall" else on[spec.id])
    }
    return Providers(
        # No email: unlike the sources, a PDF host (arxiv.org, a publisher, a repository, or a redirect target) never
        # agreed to receive the owner's email.
        pdf=httpx.AsyncClient(
            timeout=PDF_TIMEOUT, follow_redirects=True, headers={"User-Agent": PDF_USER_AGENT}, transport=transport,
            event_hooks={"request": [pdf_links.guard]},  # every hop, redirects included
        ),
        clients=clients,
    )


@asynccontextmanager
async def open_providers(session: AsyncSession) -> AsyncIterator[Providers]:
    """The clients for one request or tool call, from Settings → Paper sources, closed after it. With
    DISCOVERY_PROVIDER=fake every source answers offline (E2E)."""
    sources = await paper_sources.get(session)
    transport = None
    if settings.discovery_provider == "fake":
        transport = discovery_fake.transport()
        # The fake answers Unpaywall offline, so its placeholder can stand in for the email Unpaywall needs.
        sources = replace(sources, contact_email=sources.contact_email or discovery_fake.MAILTO)
    providers = build_providers(sources, transport)
    if transport is not None:
        providers.pdf.event_hooks["request"].clear()  # the fake's hosts never resolve, and nothing leaves the process
    try:
        yield providers
    finally:
        await providers.aclose()
