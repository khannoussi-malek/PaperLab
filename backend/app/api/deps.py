from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import discovery, llm_connections
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


async def get_discovery() -> AsyncIterator[discovery.Providers]:
    """Find papers' and Similar's clients for one request, closed after it. Tests override this with fakes."""
    fake = settings.discovery_provider == "fake"
    mailto = settings.openalex_mailto or (discovery_fake.MAILTO if fake else "")
    transport = discovery_fake.transport() if fake else None
    providers = discovery.build_providers(mailto, settings.semantic_scholar_api_key, transport)
    try:
        yield providers
    finally:
        await providers.aclose()


DiscoveryDep = Annotated[discovery.Providers, Depends(get_discovery)]
