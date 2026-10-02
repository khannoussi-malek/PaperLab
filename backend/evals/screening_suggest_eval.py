"""M31b accuracy gate (spec §6): run the screening prompt over a workspace's already-decided hits with the default
chat model, and compare with the reader's own decisions. The chip UI ships only when this passes.

    docker compose exec api python -m evals.screening_suggest_eval --workspace "My survey"
"""

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass

from app.core import llm_connections, workspaces
from app.core.screening import hit_text, load_pool
from app.core.screening_suggest import SYSTEM_PROMPT, build_prompt, parse_reply
from app.db import SessionLocal
from app.providers.llm import build_llm

MAX_MISSED_RELEVANT = 0.05
MIN_DECIDED = 100
MIN_POSITIVES = 10


@dataclass(frozen=True)
class Metrics:
    decided: int
    positives: int
    missed_relevant_rate: float
    exclude_precision: float | None
    unsure_share: float
    median_seconds: float
    passed: bool


def score(pairs: list[tuple[str, str]], seconds: list[float]) -> Metrics:
    """`pairs`: (reader's stage1_status, model's verdict) per decided hit."""
    positives = [verdict for status, verdict in pairs if status in ("relevant", "maybe")]
    excludes = [status for status, verdict in pairs if verdict == "exclude"]
    missed = positives.count("exclude") / len(positives) if positives else 1.0
    return Metrics(
        decided=len(pairs),
        positives=len(positives),
        missed_relevant_rate=missed,
        exclude_precision=excludes.count("not_relevant") / len(excludes) if excludes else None,
        unsure_share=sum(verdict == "unsure" for _, verdict in pairs) / len(pairs) if pairs else 0.0,
        median_seconds=statistics.median(seconds) if seconds else 0.0,
        passed=len(pairs) >= MIN_DECIDED and len(positives) >= MIN_POSITIVES and missed <= MAX_MISSED_RELEVANT,
    )


async def run(workspace_name: str) -> Metrics:
    async with SessionLocal() as session:
        workspace_id = await workspaces.by_name(session, workspace_name)
        pool = await load_pool(session, workspace_id)
        if not pool.workspace.screening_criteria:
            sys.exit("This workspace has no screening criteria yet.")
        connection, model = await llm_connections.resolve(session, None)
        llm = build_llm(connection, model.name)
        pairs, seconds = [], []
        for hit, ref in pool.rows:
            if hit.stage1_status is None or not hit_text(hit, ref).strip():
                continue
            prompt = build_prompt(pool.workspace.screening_criteria, ref.title if ref else hit.normalized_title,
                                  ref.abstract if ref else None)
            start = time.perf_counter()
            reply = "".join([token async for token in llm.stream(SYSTEM_PROMPT, prompt)])
            seconds.append(time.perf_counter() - start)
            pairs.append((hit.stage1_status, parse_reply(reply).verdict))
            print(f"{len(pairs)}: {hit.stage1_status} -> {pairs[-1][1]}", flush=True)
        return score(pairs, seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    metrics = asyncio.run(run(parser.parse_args().workspace))
    print(metrics)
    print("PASS" if metrics.passed else "FAIL: missed-relevant rate over 5%, or too few decided hits")
    sys.exit(0 if metrics.passed else 1)


if __name__ == "__main__":
    main()
