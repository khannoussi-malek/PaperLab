from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import charts, chat, datasets, discovery, embedding, health, links, llm, notes, papers, workspaces
from app.api import mcp as mcp_api
from app.api import paper_sources as paper_sources_api
from app.api import references as references_api
from app.config import settings
from app.core import llm_connections, paper_sources
from app.core.errors import Conflict, DomainError, InvalidInput, NotFound
from app.db import SessionLocal

STATUS_BY_ERROR = {NotFound: 404, InvalidInput: 422, Conflict: 409}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    async with SessionLocal() as session:
        await llm_connections.seed_from_env(
            session, settings.llm_provider, settings.llm_model, settings.ollama_url, settings.anthropic_api_key
        )
        await paper_sources.seed_from_env(session, settings.openalex_mailto, settings.semantic_scholar_api_key)
    yield
    await app.state.arq.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="PaperLab", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(papers.router)
    app.include_router(notes.router)
    app.include_router(chat.router)
    app.include_router(workspaces.router)
    app.include_router(datasets.router)
    app.include_router(charts.router)
    app.include_router(llm.router)
    app.include_router(embedding.router)
    app.include_router(discovery.router)
    app.include_router(paper_sources_api.router)
    app.include_router(references_api.router)
    app.include_router(links.router)
    app.include_router(mcp_api.router)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=STATUS_BY_ERROR.get(type(exc), 400))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's own handler echoes each error's `input`, and a model-level error echoes the whole body: an API
        # key sent in the wrong shape would come back in the response. Same body otherwise.
        errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

    return app


app = create_app()
