import logging

from arq.connections import RedisSettings

from app.config import settings
from app.workers.ingest import ingest_paper

logging.basicConfig(level=logging.INFO)


class WorkerSettings:
    functions = [ingest_paper]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
