"""Task 16 (R18): the paper-merges report. A dry run by default; --apply merges only a proven, ready candidate."""

import pytest
from sqlalchemy import func, select
from test_paper_merges import kept, merged

from app.models import Paper, PaperMerge
from app.scripts import paper_merges

pytestmark = pytest.mark.anyio

PMC = "PMC123456"


async def seed(session):
    """Three PDF-less papers, each the same work as a PDF paper: one proven by a shared PMCID and ready, one proven but
    not ready, one title only."""
    proven_k = await kept(session, doi="10.1/proven", title="Proven work", pmcid=PMC)
    proven_m = await merged(session, title="Proven work", pmcid=PMC, openalex_id="W1")
    waiting_k = await kept(session, doi="10.1/waiting", title="Waiting work", pmcid="PMC2")
    waiting_m = await merged(session, title="Waiting work", pmcid="PMC2", openalex_id="W2", status="processing")
    title_k = await kept(session, doi="10.1/title", title="Title only work")
    title_m = await merged(session, title="Title only work", openalex_id="W3")
    session.add(PaperMerge(kept_id=title_k.id, merged_id=title_m.id, status="reported", reason="old"))
    await session.commit()
    return proven_k, proven_m, waiting_k, waiting_m, title_k, title_m


async def counts(session) -> tuple[int, int]:
    return (
        await session.scalar(select(func.count()).select_from(Paper)),
        await session.scalar(select(func.count()).select_from(PaperMerge)),
    )


async def test_a_dry_run_lists_the_audit_and_candidates_and_changes_nothing(session):
    proven_k, proven_m, *_ = await seed(session)
    before = await counts(session)
    report = await paper_merges.run(session)
    assert await counts(session) == before
    assert [r.reason for r in report.audit if r.reason == "old"] == ["old"]
    by_kept = {c.kept_id: c for c in report.candidates}
    proven = by_kept[proven_k.id]
    assert (proven.merged_id, proven.proof, proven.ready, proven.applied) == (proven_m.id, f"pmcid:{PMC}", True, None)
    assert proven.result.status == "merged" and proven.result.dry_run
    assert [c.result.reason for c in report.candidates if c.proof == "title only"] == ["no_shared_identifier"]
    assert "Dry run" in paper_merges.render(report, apply=False)


async def test_apply_merges_only_a_proven_ready_candidate(session):
    proven_k, proven_m, waiting_k, waiting_m, title_k, title_m = await seed(session)
    report = await paper_merges.run(session, apply=True)
    applied = [c for c in report.candidates if c.applied]
    assert [c.kept_id for c in applied] == [proven_k.id]
    assert applied[0].applied.status == "merged"
    assert await session.get(Paper, proven_m.id) is None
    for left in (waiting_m, title_m):
        assert await session.get(Paper, left.id) is not None
    row = await session.scalar(select(PaperMerge).where(PaperMerge.merged_id == proven_m.id))
    assert row.status == "merged"


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exit_:
        paper_merges.cli(["--help"])
    assert exit_.value.code == 0
    assert "--apply" in capsys.readouterr().out
