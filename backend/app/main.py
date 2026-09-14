from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import chat, health, notes, papers, workspaces
from app.config import settings
from app.core.errors import Conflict, DomainError, InvalidInput, NotFound

STATUS_BY_ERROR = {NotFound: 404, InvalidInput: 422, Conflict: 409}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="PaperLab", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(papers.router)
    app.include_router(notes.router)
    app.include_router(chat.router)
    app.include_router(workspaces.router)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=STATUS_BY_ERROR.get(type(exc), 400))

    return app


app = create_app()
