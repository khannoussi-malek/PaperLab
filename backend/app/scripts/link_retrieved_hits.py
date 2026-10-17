"""Links every failed search hit whose paper is already in its workspace to that paper, as `imported` (M67).

Run once in the api container, after a backup: `python -m app.scripts.link_retrieved_hits [--dry-run]`. Idempotent:
a second run links nothing. `--dry-run` prints what it would link and changes nothing. Papers are never touched.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.core import retrieved_hits
from app.db import SessionLocal
from app.models import Paper
from app.models.workspace_search import WorkspaceSearchHit


async def main(dry_run: bool) -> None:
    async with SessionLocal() as session:
        linked = await retrieved_hits.repair(session)
        titles = dict(
            (
                await session.execute(select(Paper.id, Paper.title).where(Paper.id.in_([f.paper_id for f in linked])))
            ).all()
        )
        hits = dict(
            (await session.execute(
                select(WorkspaceSearchHit.id, WorkspaceSearchHit.normalized_title)
                .where(WorkspaceSearchHit.id.in_([f.hit_id for f in linked]))
            )).all()
        )  # fmt: skip
        await (session.rollback() if dry_run else session.commit())
    for found in linked:  # every link, with its rule, so a title match can be checked by eye before the real run
        print(f"{found.rule:<10} {hits[found.hit_id]!r} -> {titles[found.paper_id]!r} (hit {found.hit_id})")
    print({"linked": len(linked), "by_title": sum(f.rule == "title" for f in linked), "dry_run": dry_run})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would be linked; change nothing")
    asyncio.run(main(parser.parse_args().dry_run))
