import asyncio
import logging

from arq.connections import RedisSettings

from app.config import settings
from app.providers import embedding
from app.workers.ingest import ingest_paper, reembed_paper
from app.workers.references import fetch_references

logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    """Once per worker process, not per job: loading the model takes ~6 s and ~450 MB."""
    ctx["embedder"] = await asyncio.to_thread(embedding.load)


class WorkerSettings:
    functions = [ingest_paper, reembed_paper, fetch_references]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
