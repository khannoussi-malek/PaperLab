"""A manuscript's paperlab.bib: the workspace's papers as BibTeX, with the keys the source cites pinned (M27a)."""

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import workspaces
from app.core.citations_export import _bibtex, bibtex_keys, csl_item
from app.models import Manuscript, ManuscriptCiteKey

CITE = re.compile(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|nocite)\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}")
COMMENT = re.compile(r"(?<!\\)%.*")


def cited_keys(sources: Iterable[str]) -> list[str]:
    """The distinct keys cited, in source order. Comments (an unescaped % to the end of the line) are ignored."""
    found: dict[str, None] = {}
    for source in sources:
        text = "\n".join(COMMENT.sub("", line) for line in source.splitlines())
        for group in CITE.findall(text):
            for key in group.split(","):
                if key.strip():
                    found[key.strip()] = None
    return list(found)


async def build_bib(session: AsyncSession, manuscript: Manuscript, sources: dict[str, str]) -> str:
    """The whole .bib text. Cited keys that match a generated key are pinned; pinned entries are refreshed from their
    paper, and one whose paper is gone (or left the workspace) keeps its stored entry."""
    papers = await workspaces.papers(session, manuscript.workspace_id) if manuscript.workspace_id else []
    items = {str(p.id): csl_item(p) for p in papers}
    query = select(ManuscriptCiteKey).where(ManuscriptCiteKey.manuscript_id == manuscript.id)
    rows = {r.key: r for r in await session.scalars(query)}
    # a pin whose paper is gone still reserves its key: its own key stands in as the id
    pins = {str(r.paper_id) if r.paper_id else f"orphan:{r.key}": r.key for r in rows.values()}
    generated = {key: pid for pid, key in bibtex_keys(list(items.values()), pins).items()}
    for key in cited_keys(sources.values()):
        if key in generated and key not in rows:
            rows[key] = ManuscriptCiteKey(
                manuscript_id=manuscript.id, key=key, paper_id=uuid.UUID(generated[key]), bibtex=""
            )
            session.add(rows[key])
            pins[generated[key]] = key
    for row in rows.values():
        if row.paper_id and (item := items.get(str(row.paper_id))):
            row.bibtex = _bibtex([item], {item["id"]: row.key})
    await session.flush()
    orphans = [r.bibtex for _, r in sorted(rows.items()) if str(r.paper_id) not in items]
    return _bibtex(list(items.values()), pins) + "".join(orphans)
