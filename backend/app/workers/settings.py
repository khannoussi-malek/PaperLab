import logging

from arq import func
from arq.connections import RedisSettings

from app.config import settings
from app.workers.ingest import ingest_paper, reembed_paper
from app.workers.references import fetch_references
from app.workers.workspace_search import SEARCH_RUN_JOB_TIMEOUT, run_workspace_search

logging.basicConfig(level=logging.INFO)
# SEARCH_RUN_JOB_TIMEOUT lives in workers/workspace_search.py, not here — the worker's own wall-clock deadline
# check (C2 Important 1) is computed from that same constant, so importing it (rather than redefining a second
# copy here) means the registered job_timeout and the loop's own backstop can never drift apart.


class WorkerSettings:
    # No on_startup: the search model loads on the first job that needs it, once it is downloaded (D136).
    functions = [
        ingest_paper,
        reembed_paper,
        fetch_references,
        func(run_workspace_search, timeout=SEARCH_RUN_JOB_TIMEOUT),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
