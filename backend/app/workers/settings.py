import logging

from arq.connections import RedisSettings

from app.config import settings
from app.workers.ingest import ingest_paper, reembed_paper
from app.workers.references import fetch_references

logging.basicConfig(level=logging.INFO)


class WorkerSettings:
    # No on_startup: the search model loads on the first job that needs it, once it is downloaded (D136).
    functions = [ingest_paper, reembed_paper, fetch_references]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
