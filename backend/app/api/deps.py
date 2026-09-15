from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_transport() -> httpx.AsyncBaseTransport | None:
    """None: provider calls go out for real. Tests override it with an httpx.MockTransport."""
    return None


TransportDep = Annotated[httpx.AsyncBaseTransport | None, Depends(get_transport)]
