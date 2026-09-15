import asyncio
import logging

from arq.connections import RedisSettings

from app.config import settings
from app.providers import embedding, openalex
from app.workers.ingest import ingest_paper, reembed_paper

logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    """Once per worker process, not per job: loading the model takes ~6 s and ~450 MB."""
    ctx["embedder"] = await asyncio.to_thread(embedding.load)
    ctx["openalex"] = openalex.new_client(settings.openalex_mailto) if settings.openalex_mailto else None


async def shutdown(ctx: dict) -> None:
    if ctx.get("openalex"):
        await ctx["openalex"].aclose()


class WorkerSettings:
    functions = [ingest_paper, reembed_paper]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
