import logging

from arq import func
from arq.connections import RedisSettings

from app.config import settings
from app.workers.ingest import ingest_paper, reembed_paper
from app.workers.references import fetch_references
from app.workers.workspace_search import run_workspace_search

logging.basicConfig(level=logging.INFO)

# ARQ's own default job_timeout is 300s. A search run's own bounded retry/pacing/iteration-cap (C2 parts 1-3)
# should finish well inside this window in practice; this is defense in depth, not the primary fix — without it,
# a run that somehow ran long would get cancelled by the default timeout (asyncio.CancelledError, a BaseException
# the worker's `except Exception` doesn't catch) and left stuck at status="running" forever.
SEARCH_RUN_JOB_TIMEOUT = 1800
# ponytail: a hard kill mid-commit (e.g. a true ARQ-level cancellation past even this longer timeout) could still
# rarely leave a run stuck at "running" — full cancellation-safe cleanup (asyncio.shield around the final status
# write) is a known ceiling, not solved here, since parts 1-3 make it very unlikely in practice.


class WorkerSettings:
    # No on_startup: the search model loads on the first job that needs it, once it is downloaded (D136).
    functions = [
        ingest_paper,
        reembed_paper,
        fetch_references,
        func(run_workspace_search, timeout=SEARCH_RUN_JOB_TIMEOUT),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
