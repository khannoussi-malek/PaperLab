import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import discovery, llm_connections, paper_sources
from app.db import get_session
from app.providers import discovery_fake
from app.providers.base import LLM
from app.providers.llm import build_llm
from app.schemas.chat import ChatRequest

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_transport() -> httpx.AsyncBaseTransport | None:
    """None: provider calls go out for real. Tests override it with an httpx.MockTransport."""
    return None


TransportDep = Annotated[httpx.AsyncBaseTransport | None, Depends(get_transport)]


async def resolve_llm(payload: ChatRequest, session: SessionDep, transport: TransportDep) -> LLM:
    """The adapter for the question's model, or the default's. Declared before the route's prepare dependency, so it
    runs before retrieval and before the stream starts: 404 model_not_found and 409 no_model are plain responses."""
    connection, model = await llm_connections.resolve(session, payload.model_id)
    return build_llm(connection, model.name, transport=transport)


LLMDep = Annotated[LLM, Depends(resolve_llm)]


async def resolve_llm_by_model_id(
    session: SessionDep, transport: TransportDep, model_id: uuid.UUID | None = None
) -> LLM:
    """Same resolution as resolve_llm, for a route with no ChatRequest body to carry model_id — note suggestions
    take no question, just an optional model to pick."""
    connection, model = await llm_connections.resolve(session, model_id)
    return build_llm(connection, model.name, transport=transport)


LLMByModelIdDep = Annotated[LLM, Depends(resolve_llm_by_model_id)]


async def get_discovery(session: SessionDep) -> AsyncIterator[discovery.Providers]:
    """Find papers' and Similar's clients for one request, from Settings → Paper sources, closed after it. Tests
    override this with fakes."""
    sources = await paper_sources.get(session)
    transport = None
    if settings.discovery_provider == "fake":
        transport = discovery_fake.transport()
        # The fake answers Unpaywall offline, so its placeholder can stand in for the email Unpaywall needs.
        sources = replace(sources, contact_email=sources.contact_email or discovery_fake.MAILTO)
    providers = discovery.build_providers(sources, transport)
    try:
        yield providers
    finally:
        await providers.aclose()


DiscoveryDep = Annotated[discovery.Providers, Depends(get_discovery)]
