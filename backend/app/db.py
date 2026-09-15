from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# hide_parameters: a DBAPIError's text otherwise includes every bound parameter of the failing statement, an
# API key among them (create_connection, update_connection, and the seed insert all write one).
engine = create_async_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)

# expire_on_commit=False: touching an attribute after commit would otherwise lazy-load,
# which raises MissingGreenlet under asyncio.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
