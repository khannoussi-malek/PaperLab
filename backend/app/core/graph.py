"""How library papers connect, derived when asked (D88): nothing is stored and the `edges` table stays unused.

Link kinds, each read from the table that already holds it:
- same_workspace: both papers are in one workspace (workspace_papers)
- co_anchored: one note is anchored on both (note_anchors)
- co_authored: they share an author (paper_authors)
- shares_topic: they share a topic label, any source, ignoring case (paper_topics)
- cites / cited_by: one paper's reference is the other (paper_references + external_refs, M7.5). A reference is a
  library paper the way the References tab shows it In library: its imported_as, else a paper with the same
  openalex_id, DOI or arXiv DOI.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidInput
from app.core.papers import get_paper

MAX_HOPS = 3

# The walk is a UNION over (paper, hops, kind): hops is bounded, so a cycle ends, and each step keeps a set of rows
# instead of enumerating paths. Each paper is then reported at its nearest distance, with the kinds that reached it
# there.
# ponytail: every call derives every link in the library (~50 ms at 60 papers with 600 references each); store edges or
# walk from the asked paper outward if a real library makes it slow.
_RELATED = text(
    """
    WITH RECURSIVE in_library(ref_id, paper_id) AS (
      SELECT id, imported_as FROM external_refs WHERE imported_as IS NOT NULL
      UNION SELECT r.id, p.id FROM external_refs r JOIN papers p ON p.openalex_id = r.openalex_id
             WHERE r.imported_as IS NULL
      UNION SELECT r.id, p.id FROM external_refs r JOIN papers p ON lower(p.doi) = lower(r.doi)
             WHERE r.imported_as IS NULL
      UNION SELECT r.id, p.id FROM external_refs r
               JOIN papers p ON lower(p.doi) = '10.48550/arxiv.' || lower(r.arxiv_id)
             WHERE r.imported_as IS NULL
    ), citations(citing, cited) AS (
      SELECT pr.paper_id, l.paper_id FROM paper_references pr JOIN in_library l ON l.ref_id = pr.ref_id
       WHERE pr.direction = 'cites'
      UNION SELECT l.paper_id, pr.paper_id FROM paper_references pr JOIN in_library l ON l.ref_id = pr.ref_id
       WHERE pr.direction = 'cited_by'
    ), edges(src, dst, via) AS (
      SELECT a.paper_id, b.paper_id, 'same_workspace' FROM workspace_papers a
        JOIN workspace_papers b ON b.workspace_id = a.workspace_id AND b.paper_id <> a.paper_id
      UNION SELECT a.paper_id, b.paper_id, 'co_anchored' FROM note_anchors a
        JOIN note_anchors b ON b.note_id = a.note_id AND b.paper_id <> a.paper_id
      UNION SELECT a.paper_id, b.paper_id, 'co_authored' FROM paper_authors a
        JOIN paper_authors b ON b.author_id = a.author_id AND b.paper_id <> a.paper_id
      UNION SELECT a.paper_id, b.paper_id, 'shares_topic' FROM paper_topics a
        JOIN paper_topics b ON lower(b.label) = lower(a.label) AND b.paper_id <> a.paper_id
      UNION SELECT citing, cited, 'cites' FROM citations WHERE citing <> cited
      UNION SELECT cited, citing, 'cited_by' FROM citations WHERE citing <> cited
    ), walk(paper_id, hops, via) AS (
      SELECT dst, 1, via FROM edges WHERE src = :paper_id
      UNION
      SELECT e.dst, w.hops + 1, e.via FROM walk w JOIN edges e ON e.src = w.paper_id WHERE w.hops < :hops
    ), nearest AS (
      SELECT paper_id, min(hops) AS hops FROM walk WHERE paper_id <> :paper_id GROUP BY paper_id
    )
    SELECT n.paper_id, p.title, p.year, n.hops, array_agg(DISTINCT w.via ORDER BY w.via) AS via
      FROM nearest n
      JOIN walk w ON w.paper_id = n.paper_id AND w.hops = n.hops
      JOIN papers p ON p.id = n.paper_id
     GROUP BY n.paper_id, p.title, p.year, n.hops
     ORDER BY n.hops, count(DISTINCT w.via) DESC, p.title
    """
)


@dataclass(frozen=True)
class Related:
    paper_id: uuid.UUID
    title: str
    year: int | None
    hops: int  # the fewest links from the asked paper
    via: list[str]  # the kinds of link that reached it at that distance, alphabetical


async def related(session: AsyncSession, paper_id: uuid.UUID, hops: int = 1) -> list[Related]:
    """Library papers within `hops` links of this one, nearest first, then most kinds of link, then title.

    Raises InvalidInput("hops_out_of_range", allowed=[1, MAX_HOPS]), NotFound.
    """
    if not 1 <= hops <= MAX_HOPS:
        raise InvalidInput("hops_out_of_range", allowed=[1, MAX_HOPS])
    await get_paper(session, paper_id)
    rows = await session.execute(_RELATED, {"paper_id": paper_id, "hops": hops})
    return [Related(row.paper_id, row.title, row.year, row.hops, list(row.via)) for row in rows]
