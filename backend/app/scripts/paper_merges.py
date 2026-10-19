"""Reports the paper merges (merged and refused) and the pairs that could still be merged: a PDF paper (M) that is the
same work as a paper saved without a PDF (K).

Run in the api container: `python -m app.scripts.paper_merges`. A dry run by default: it writes nothing. `--apply`
merges the candidates whose dry run says it would, whose M is ready, and that share an identifier. A pair matched by
title alone is never applied, only listed for review.
"""

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discovery, merges
from app.core.candidates import Candidate, normal_title
from app.db import SessionLocal
from app.models import Paper, PaperMerge


@dataclass(frozen=True)
class MergeCandidate:
    kept_id: uuid.UUID
    merged_id: uuid.UUID
    kept_title: str
    proof: str  # the shared identifier ("pmcid:PMC1"), or "title only"
    result: merges.MergeResult  # the dry run
    ready: bool  # M's ingest is done
    applied: merges.MergeResult | None = None

    @property
    def applicable(self) -> bool:
        return self.result.status == "merged" and self.ready and self.proof != "title only"


@dataclass(frozen=True)
class Report:
    audit: list[PaperMerge] = field(default_factory=list)
    candidates: list[MergeCandidate] = field(default_factory=list)


def _proof(kept: Paper, merged: Paper) -> str:
    for column in merges.IDENTIFIERS:
        ours = merges._normal(column, getattr(kept, column))
        if ours and ours == merges._normal(column, getattr(merged, column)):
            return f"{column}:{ours}"
    return "title only"


async def _pairs(session: AsyncSession) -> list[tuple[Paper, Paper]]:
    """(K, M) for every PDF-less K and PDF paper M with the same normalised title that are the same work.
    ponytail: reads every PDF paper's id and title once; index a normalised title column if libraries get huge."""
    pdfless = list(await session.scalars(select(Paper).where(Paper.file_path.is_(None)).order_by(Paper.created_at)))
    wanted = {normal_title(k.title) for k in pdfless}
    by_title: dict[str, list[uuid.UUID]] = {}
    for paper_id, title in await session.execute(select(Paper.id, Paper.title).where(Paper.file_path.is_not(None))):
        if (key := normal_title(title)) in wanted:
            by_title.setdefault(key, []).append(paper_id)
    found = {p.id: p for p in await session.scalars(select(Paper).where(Paper.id.in_(sum(by_title.values(), []))))}
    pairs = []
    for k in pdfless:
        for m_id in by_title.get(normal_title(k.title), []):
            m = found[m_id]
            theirs = {"title": m.title, "authors": m.authors, "year": m.year}
            if discovery.same_work(Candidate(k.title, k.authors, k.year), theirs):
                pairs.append((k, m))
    return pairs


async def run(session: AsyncSession, *, apply: bool = False) -> Report:
    audit = list(await session.scalars(select(PaperMerge).order_by(PaperMerge.created_at)))
    session.expunge_all()  # merge needs a session with nothing pending; the rows stay readable
    candidates = []
    for k, m in await _pairs(session):
        kept_id, merged_id, title, proof, ready = k.id, m.id, k.title, _proof(k, m), m.status == "ready"
        session.expunge_all()
        result = await merges.merge(session, merged_id, kept_id, dry_run=True)
        candidate = MergeCandidate(kept_id, merged_id, title, proof, result, ready)
        if apply and candidate.applicable:
            # "imported": the merge has no better word for a script-run merge
            candidate = MergeCandidate(
                kept_id, merged_id, title, proof, result, ready,
                await merges.merge(session, merged_id, kept_id, how="imported"),
            )  # fmt: skip
        candidates.append(candidate)
    return Report(audit, candidates)


def _describe(result: merges.MergeResult) -> str:
    return f"merged {result.moved}" if result.status == "merged" else f"reported: {result.reason}"


def render(report: Report, *, apply: bool) -> str:
    lines = ["Audit:"]
    for row in report.audit:
        when = row.created_at.strftime("%Y-%m-%d")
        lines.append(
            f"  {when} {row.status} kept={row.kept_id} merged={row.merged_id} {row.reason or ''} {row.identifier or ''}"
        )
    done = sum(r.status == "merged" for r in report.audit)
    lines.append(f"  {done} merged, {len(report.audit) - done} reported")
    lines.append("Candidates:")
    for c in report.candidates:
        verdict = "for review (title only)" if c.proof == "title only" else "ready" if c.ready else "M not ready"
        lines.append(
            f"  kept={c.kept_id} merged={c.merged_id} {c.kept_title!r} proof={c.proof} "
            f"dry run: {_describe(c.result)} [{verdict}]"
        )
        if c.applied:
            lines.append(f"    applied: {_describe(c.applied)}")
    mode = "Applied." if apply else "Dry run: nothing was written. Pass --apply to merge the proven, ready ones."
    lines.append(f"{len(report.candidates)} candidates. {mode}")
    return "\n".join(lines)


async def main(apply: bool = False) -> None:
    async with SessionLocal() as session:
        print(render(await run(session, apply=apply), apply=apply))


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="merge the proven, ready candidates (default: dry run)")
    asyncio.run(main(apply=parser.parse_args(argv).apply))


if __name__ == "__main__":
    cli()
