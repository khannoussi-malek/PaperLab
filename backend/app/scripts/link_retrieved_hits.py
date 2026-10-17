"""Links every failed search hit whose paper is already in its workspace to that paper, as `imported` (M67).

Run once in the api container, after a backup: `python -m app.scripts.link_retrieved_hits [--dry-run]`. Idempotent:
a second run links nothing. `--dry-run` prints what it would link and changes nothing. Papers are never touched.
"""

import argparse
import asyncio

from app.core import retrieved_hits
from app.db import SessionLocal


async def main(dry_run: bool) -> None:
    async with SessionLocal() as session:
        linked = await retrieved_hits.repair(session)
        await (session.rollback() if dry_run else session.commit())
    print({"linked": len(linked), "dry_run": dry_run, "hit_ids": [str(h) for h in linked]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would be linked; change nothing")
    asyncio.run(main(parser.parse_args().dry_run))
