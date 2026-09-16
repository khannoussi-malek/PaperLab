from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections
from app.db import get_session
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
