"""Keys a manuscript cites that match no library paper, pinned key or entry in the user's own .bib files (M27d)."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.manuscript_bib import key_state
from app.core.manuscript_paths import RESERVED
from app.core.manuscript_sentences import cite_spans
from app.models import ManuscriptFile

ENTRY = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
NOT_ENTRIES = {"comment", "string", "preamble"}


async def missing_keys(session: AsyncSession, mid: uuid.UUID) -> list[dict]:
    """One {key, file, line} per occurrence, files in path order."""
    manuscript = await manuscripts.get(session, mid)
    query = (
        select(ManuscriptFile.path, ManuscriptFile.text)
        .where(ManuscriptFile.manuscript_id == mid, ManuscriptFile.text.is_not(None))
        .order_by(ManuscriptFile.path)
    )
    files = [(path, text) for path, text in await session.execute(query)]
    _, rows, _, generated = await key_state(session, manuscript)
    known = set(generated) | set(rows)
    for path, text in files:
        if path.endswith(".bib") and path != RESERVED:
            known |= {m[1] for m in ENTRY.findall(text) if m[0].lower() not in NOT_ENTRIES}
    return [
        {"key": key, "file": path, "line": line}
        for path, text in files
        if path.endswith(".tex")
        for key, line in cite_spans(text)
        if key not in known
    ]
