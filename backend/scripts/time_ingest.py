"""Uploads one PDF to a PaperLab stack and prints when each ingest stage was first seen.

    uv run python -m scripts.time_ingest paper.pdf --api http://localhost:8100

Run it against a test stack (scripts/e2e-stack.sh), never the live API: it adds a paper. Timings are as seen by a poll
every POLL_SECONDS, so each is good to about that much.
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

POLL_SECONDS = 2
LIVE_PORT = 8000
TERMINAL = ("ready", "failed")


@dataclass(frozen=True)
class Timing:
    stages: dict[str, float]  # stage -> seconds after the first poll that it was first seen
    final: str
    total: float
    error: str | None


def normalise_api(api: str) -> str:
    """`localhost:8100` parses with no port (urlparse takes `localhost` for a scheme), so add the scheme first."""
    return api if "://" in api else f"http://{api}"


def check_not_live(api: str, allowed: bool) -> None:
    if urlparse(api).port == LIVE_PORT and not allowed:
        sys.exit(f"{api} is the live API (port {LIVE_PORT}); use a test stack, or pass --i-know-this-is-live")


def track(client: httpx.Client, paper_id: str, timeout: float, clock=time.monotonic, sleep=time.sleep) -> Timing:
    """Polls the paper until it is ready or failed, or `timeout` seconds pass."""
    start = clock()
    stages: dict[str, float] = {}
    while True:
        paper = client.get(f"/api/papers/{paper_id}").raise_for_status().json()
        elapsed = clock() - start
        stages.setdefault(paper["status"], elapsed)
        if paper["status"] in TERMINAL or elapsed >= timeout:
            return Timing(stages, paper["status"], elapsed, paper.get("status_error"))
        sleep(POLL_SECONDS)


def report(timing: Timing) -> str:
    lines = [f"{stage:<11} first seen at {at:7.1f}s" for stage, at in timing.stages.items()]
    lines.append(f"{timing.final} after {timing.total:.1f}s" + (f": {timing.error}" if timing.error else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--timeout", type=float, default=3600, help="seconds to wait for ready or failed")
    parser.add_argument("--workspace-id", help="also add the paper to this workspace")
    parser.add_argument("--i-know-this-is-live", action="store_true", help="allow the live API's port (8000)")
    args = parser.parse_args(argv)
    args.api = normalise_api(args.api)
    check_not_live(args.api, args.i_know_this_is_live)
    data = {"workspace_id": args.workspace_id} if args.workspace_id else {}
    with httpx.Client(base_url=args.api, timeout=60) as client:
        with args.pdf.open("rb") as f:
            created = client.post("/api/papers", files={"file": (args.pdf.name, f, "application/pdf")}, data=data)
        paper_id = created.raise_for_status().json()["id"]
        print(f"uploaded {args.pdf.name} as {paper_id}", flush=True)
        timing = track(client, paper_id, args.timeout)
    print(report(timing))
    return 0 if timing.final == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
