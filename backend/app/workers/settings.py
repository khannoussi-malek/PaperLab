import asyncio
import logging

from arq.connections import RedisSettings

from app.config import settings
from app.providers import embedding
from app.workers.ingest import ingest_paper

logging.basicConfig(level=logging.INFO)


async def load_embedder(ctx: dict) -> None:
    """Once per worker process, not per job: loading takes ~6 s and ~450 MB."""
    ctx["embedder"] = await asyncio.to_thread(embedding.load)


class WorkerSettings:
    functions = [ingest_paper]
    on_startup = load_embedder
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
