"""The answer check job (M34): fills a check's sentences one by one; any crash leaves it "failed", never "running"."""

import logging
import uuid

from app.core import answer_check_run
from app.db import SessionLocal

logger = logging.getLogger(__name__)


async def check_answer(ctx: dict, check_id: str) -> None:
    cid = uuid.UUID(check_id)
    try:
        async with SessionLocal() as session:
            await answer_check_run.run_check(session, cid, llm=ctx.get("llm"))
    except Exception:
        logger.exception("answer check %s failed", check_id)
        async with SessionLocal() as session:
            await answer_check_run.mark_failed(session, cid)
