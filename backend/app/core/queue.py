"""Enqueue ARQ jobs from outside a FastAPI request, i.e. the MCP server (M39 F1). The API keeps app.state.arq."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings

# A paper's ingest, re-embed and abstract index run one at a time on their own worker
# (workers.settings.IngestWorkerSettings): ten at once ran the worker out of memory (2026-10-13). Every enqueue of these
# jobs passes _queue_name=INGEST_QUEUE.
INGEST_QUEUE = "arq:ingest"
INGEST_JOBS = frozenset({"ingest_paper", "reembed_paper", "index_abstract"})

_pool: ArqRedis | None = None  # tests replace it with conftest.FakeArq


async def pool() -> ArqRedis:
    """The process's arq pool, made on first use (the MCP server also reads job status through it)."""
    # ponytail: one module-level pool for the process's life; the MCP server is one stdio process.
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue(job: str, *args, job_id: str | None = None) -> bool:
    """Queues a job; False when `job_id` is already queued or running (arq refuses the duplicate)."""
    queued = await (await pool()).enqueue_job(
        job, *args, _queue_name=INGEST_QUEUE if job in INGEST_JOBS else None, **({"_job_id": job_id} if job_id else {})
    )
    return queued is not None
