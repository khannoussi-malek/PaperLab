"""One report over every file the reviewer checked (S2P B6): JSON for the studio and the MCP, Markdown to download.
It repeats the researcher's sentences and the papers' passages; it never writes replacement wording (D118)."""

import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.errors import NotFound
from app.core.manuscript_review import LIVE, _item_status, _latest, run_out
from app.models import ManuscriptClaimCheck as Check
from app.models import ManuscriptClaimDismissal, Paper

LABELS = {
    "supported": "Supported",
    "partially_supported": "Partly supported",
    "not_supported": "Contradicted",
    "not_addressed": "Not found in the paper",
    "cannot_verify": "Could not check",
    "claim": "Uncited claim",
    "not_claim": "Not a claim",
    "unfinished": "Not finished",
}
ATTENTION = ("not_supported", "not_addressed", "cannot_verify", "claim", "unfinished")  # listed before the rest


async def build(session: AsyncSession, mid: uuid.UUID) -> dict:
    await manuscripts.get(session, mid)
    run = await _latest(session, mid)
    if run is None:
        raise NotFound("unknown_run")
    found = (
        await session.execute(
            select(Check, Paper.title)
            .outerjoin(Paper, Paper.id == Check.paper_id)
            .where(
                Check.run_id == run.id
            )  # this run's rows only: a per-file start leaves other files' rows with run_id NULL
            .order_by(Check.ord)
            .execution_options(populate_existing=True)
        )
    ).all()
    hidden = set(
        await session.scalars(
            select(ManuscriptClaimDismissal.sentence_hash).where(ManuscriptClaimDismissal.manuscript_id == mid)
        )
    )
    now = datetime.now(UTC)
    working = any(r.status == "running" and now - r.updated_at < LIVE for r, _ in found)
    files: dict[str, list[dict]] = {}
    counts: Counter[str] = Counter()
    dismissed = 0
    for r, title in found:
        if r.sentence_hash in hidden:
            dismissed += 1
            continue
        status = _item_status(r, working, now)
        outcome = r.verdict if status == "done" and r.verdict else "unfinished"
        counts[outcome] += 1
        files.setdefault(r.file_path, []).append(
            {
                "file": r.file_path, "ord": r.ord, "kind": r.kind, "sentence": r.sentence, "cite_key": r.cite_key,
                "paper_title": title, "status": status, "verdict": r.verdict, "outcome": outcome,
                "reason": r.reason, "quote": r.quote, "page": r.page,
            }
        )  # fmt: skip
    return {
        "run": run_out(run),
        "counts": dict(counts),
        "dismissed": dismissed,
        "files": [{"path": p, "items": items} for p, items in files.items()],
    }


def _item(it: dict) -> list[str]:
    who = f" [{it['cite_key']}]" + (f" {it['paper_title']}" if it["paper_title"] else "") if it["cite_key"] else ""
    lines = [f"- **{LABELS[it['outcome']]}**{who}: {it['sentence']}"]
    if it["reason"]:
        lines.append(f"  - {it['reason']}")
    if it["quote"]:
        quote = " ".join(it["quote"].split())
        lines.append(f"  - > {quote}" + (f" (p. {it['page']})" if it["page"] else ""))
    return lines


def render_markdown(report: dict) -> str:
    run = report["run"]
    out = ["# Citation review", "", f"Checked {run['done']} of {run['total']} ({run['status']}).", ""]
    out += ["| Result | Count |", "|---|---|"]
    out += [f"| {LABELS[k]} | {report['counts'][k]} |" for k in LABELS if k in report["counts"]]
    for f in report["files"]:
        shown = [i for i in f["items"] if i["outcome"] != "not_claim"]
        out += ["", f"## {f['path']}", ""]
        for it in sorted(shown, key=lambda i: (i["outcome"] not in ATTENTION, i["ord"])):
            out += _item(it)
    return "\n".join(out) + "\n"
