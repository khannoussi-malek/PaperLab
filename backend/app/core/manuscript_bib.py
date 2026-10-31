"""A manuscript's paperlab.bib: the workspace's papers as BibTeX, with the keys the source cites pinned (M27a)."""

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import workspaces
from app.core.citations_export import _bibtex, bibtex_keys, csl_item
from app.models import Manuscript, ManuscriptCiteKey

# Any command with "cite" in its name: natbib's \citealt, \Citet, \citeyearpar…, biblatex's \parencite, \textcite,
# \autocite… A non-citing match (\citestyle{plain}) is harmless: only keys that match a paper get pinned.
CITE = re.compile(r"\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}")
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


async def key_state(session: AsyncSession, manuscript: Manuscript):
    """(items by paper id, pin rows by key, pins {paper id: key}, generated {key: paper id}): the one place the .bib and
    the paper deck get their keys from."""
    papers = await workspaces.papers(session, manuscript.workspace_id) if manuscript.workspace_id else []
    items = {str(p.id): csl_item(p) for p in papers}
    query = select(ManuscriptCiteKey).where(ManuscriptCiteKey.manuscript_id == manuscript.id)
    rows = {r.key: r for r in await session.scalars(query)}
    # A pin whose paper is gone still reserves its key: its own key stands in as the id. So does a second pin on one
    # paper (a merge moved both papers' pins onto it): the paper keeps its first key, the other is emitted as is below.
    pins: dict[str, str] = {}
    for r in sorted(rows.values(), key=lambda r: r.key):
        pins.setdefault(str(r.paper_id) if r.paper_id else f"orphan:{r.key}", r.key)
    pins |= {f"orphan:{r.key}": r.key for r in rows.values() if r.key not in pins.values()}
    generated = {key: pid for pid, key in bibtex_keys(list(items.values()), pins).items()}
    return items, rows, pins, generated


async def build_bib(session: AsyncSession, manuscript: Manuscript, sources: dict[str, str]) -> str:
    """The whole .bib text. Cited keys that match a generated key are pinned; pinned entries are refreshed from their
    paper, and one whose paper is gone (or left the workspace) keeps its stored entry."""
    # Locks the manuscript row so a pin in flight (FOR UPDATE) commits before the pins are read (else both insert the
    # same key: a unique violation). Held until the caller's transaction ends. NO KEY UPDATE, as the rest of the app:
    # a plain FOR UPDATE would conflict with a file insert's KEY SHARE (its foreign key) and deadlock with it.
    locked = select(Manuscript.id).where(Manuscript.id == manuscript.id).with_for_update(key_share=True)
    await session.execute(locked)
    items, rows, pins, generated = await key_state(session, manuscript)
    for key in cited_keys(sources.values()):
        if key in generated and key not in rows:
            rows[key] = ManuscriptCiteKey(
                manuscript_id=manuscript.id, key=key, paper_id=uuid.UUID(generated[key]), bibtex=""
            )
            session.add(rows[key])
            pins[generated[key]] = key
    for row in rows.values():
        if row.paper_id and (item := items.get(str(row.paper_id))):
            row.bibtex = _bibtex([item], {item["id"]: row.key}, publish=True)
    await session.flush()
    # stored entries: a paper gone or out of the workspace, and a merged paper's second key
    orphans = [r.bibtex for _, r in sorted(rows.items())
               if str(r.paper_id) not in items or pins.get(str(r.paper_id)) != r.key]
    return _bibtex(list(items.values()), pins, publish=True) + "".join(orphans)
