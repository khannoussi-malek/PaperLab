"""How library papers connect, derived when asked (D88/D106): one edge definition, used by `related()` and the graph.

Link kinds, each read from the table that already holds it:
- same_workspace: both papers are in one workspace (workspace_papers)
- co_anchored: one note is linked to both (note_papers, D95). The kind keeps its name: the MCP tool returns it
- co_authored: they share an author (paper_authors)
- shares_topic: they share a topic label, any source, ignoring case (paper_topics)
- cites / cited_by: one paper's reference is the other (paper_references + external_refs, M7.5). A reference is a
  library paper the way the References tab shows it In library: its imported_as, else a paper with the same
  openalex_id, DOI or arXiv DOI.
- similar: either paper is among the other's SIMILAR_NEIGHBOURS nearest by content (D107), cosine between the
  averages of their chunk vectors
- manual: the owner drew it (paper_links, D110). It is the one stored kind; the graph also carries its label.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import embedding_sources
from app.core.errors import InvalidInput
from app.core.papers import get_paper
from app.core.workspaces import get as get_workspace

MAX_HOPS = 3
# D107: a threshold draws a hairball (every pair of the owner's papers scores >= 0.8 cosine); the top 3 are right.
SIMILAR_NEIGHBOURS = 3

# D109: one payload for the whole library. The owner's 19 papers draw 77 links (13 kB of JSON); a synthetic 300 draw
# 4,818, capped to 2,000 (300 kB) with every kind still represented.
MAX_LINKS = 2000


def _similarity(name: str) -> dict:
    """`similar`'s parameters. Only the search source's own vectors are averaged (D156): search and chat refuse to mix
    two models' vectors, and mid-rebuild a paper can still hold the old source's, so only papers already embedded
    again are linked."""
    return {"neighbours": SIMILAR_NEIGHBOURS, "embed_model": name}


# The one definition both `related()` and `library_graph()` build on (D106). Directed rows: every undirected kind is
# emitted both ways so the walk can leave a paper by any link; the graph normalises them back to one row per pair.
# ponytail: `paper_vec` re-averages every chunk vector on each call and `near` compares every pair of papers (an
# averaged vector defeats the HNSW index on chunks), so each graph load and each related() call costs about 15 us per
# chunk plus 0.7 us per pair. At the owner's real density (~69 chunks a paper) that is ~0.5 s at 300 papers, ~0.75 s
# at 500, and tens of seconds at 5,000. Store one vector per paper, and index it, before the library reaches ~300.
_EDGES = """
RECURSIVE in_library(ref_id, paper_id) AS (
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
), paper_vec(paper_id, v) AS (
  SELECT paper_id, avg(embedding) FROM chunks
   WHERE embedding IS NOT NULL AND embed_model = :embed_model GROUP BY paper_id
), near(src, dst) AS (
  SELECT src, dst FROM (
    SELECT a.paper_id AS src, b.paper_id AS dst,
           row_number() OVER (PARTITION BY a.paper_id ORDER BY a.v <=> b.v, b.paper_id) AS nth
      FROM paper_vec a JOIN paper_vec b ON b.paper_id <> a.paper_id
  ) ranked WHERE nth <= :neighbours
), edges(src, dst, via) AS (
  SELECT a.paper_id, b.paper_id, 'same_workspace' FROM workspace_papers a
    JOIN workspace_papers b ON b.workspace_id = a.workspace_id AND b.paper_id <> a.paper_id
  UNION SELECT a.paper_id, b.paper_id, 'co_anchored' FROM note_papers a
    JOIN note_papers b ON b.note_id = a.note_id AND b.paper_id <> a.paper_id
  UNION SELECT a.paper_id, b.paper_id, 'co_authored' FROM paper_authors a
    JOIN paper_authors b ON b.author_id = a.author_id AND b.paper_id <> a.paper_id
  UNION SELECT a.paper_id, b.paper_id, 'shares_topic' FROM paper_topics a
    JOIN paper_topics b ON lower(b.label) = lower(a.label) AND b.paper_id <> a.paper_id
  UNION SELECT citing, cited, 'cites' FROM citations WHERE citing <> cited
  UNION SELECT cited, citing, 'cited_by' FROM citations WHERE citing <> cited
  UNION SELECT src, dst, 'similar' FROM near
  UNION SELECT dst, src, 'similar' FROM near
  UNION SELECT from_paper, to_paper, 'manual' FROM paper_links
  UNION SELECT to_paper, from_paper, 'manual' FROM paper_links
)"""

# The walk is a UNION over (paper, hops, kind): hops is bounded, so a cycle ends, and each step keeps a set of rows
# instead of enumerating paths. Each paper is then reported at its nearest distance, with the kinds that reached it
# there.
# ponytail: shares_topic counts every stored label, OpenAlex's broad concepts ("Computer science") included, so it can
# link most of a library; filter by score (a threshold on paper_topics.score) or by topic type if it makes
# related_papers noisy.
_RELATED = text(
    f"""
    WITH {_EDGES}, walk(paper_id, hops, via) AS (
      SELECT dst, 1, via FROM edges WHERE src = :paper_id
      UNION
      -- `similar` counts for the first hop only: every paper with text has similar neighbours, so following them
      -- further reaches most of the library (owner 2026-09-18, D112).
      SELECT e.dst, w.hops + 1, e.via FROM walk w JOIN edges e ON e.src = w.paper_id
       WHERE w.hops < :hops AND e.via <> 'similar'
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

# One row per pair per kind: undirected kinds keep the smaller id first, `cites` keeps citing -> cited, and
# `cited_by` is dropped as the same link seen backwards. `manual` comes straight from paper_links with its id and
# label. The cap takes kinds round-robin (row_number per kind, ordered by that rank), so no kind is starved; asking
# for one row more than the cap is how `truncated` is known.
_GRAPH_LINKS = text(
    f"""
    WITH {_EDGES}, scope(paper_id) AS (
      SELECT p.id FROM papers p
       WHERE CAST(:workspace AS uuid) IS NULL
          OR EXISTS (SELECT 1 FROM workspace_papers wp
                      WHERE wp.paper_id = p.id AND wp.workspace_id = :workspace)
    ), links(source, target, kind, link_id, label) AS (
      SELECT DISTINCT
             CASE WHEN e.via = 'cites' THEN e.src ELSE least(e.src, e.dst) END,
             CASE WHEN e.via = 'cites' THEN e.dst ELSE greatest(e.src, e.dst) END,
             e.via, NULL::uuid, NULL::text
        FROM edges e JOIN scope a ON a.paper_id = e.src JOIN scope b ON b.paper_id = e.dst
       WHERE e.via NOT IN ('cited_by', 'manual')
      UNION ALL
      SELECT l.from_paper, l.to_paper, 'manual', l.id, l.label
        FROM paper_links l JOIN scope a ON a.paper_id = l.from_paper JOIN scope b ON b.paper_id = l.to_paper
    ), ranked AS (
      SELECT source, target, kind, link_id, label,
             row_number() OVER (PARTITION BY kind ORDER BY source, target) AS nth
        FROM links
    )
    SELECT source, target, kind, link_id, label FROM ranked ORDER BY nth, kind LIMIT :cap
    """
)

_GRAPH_NODES = text(
    """
    SELECT p.id, p.title, p.year, p.status, p.created_at AS added_at,
           coalesce((SELECT array_agg(w.name ORDER BY wp.added_at)
                       FROM workspace_papers wp JOIN workspaces w ON w.id = wp.workspace_id
                      WHERE wp.paper_id = p.id), '{}') AS workspaces,
           EXISTS (SELECT 1 FROM note_papers np WHERE np.paper_id = p.id) AS has_notes
      FROM papers p
     WHERE CAST(:workspace AS uuid) IS NULL
        OR EXISTS (SELECT 1 FROM workspace_papers wp WHERE wp.paper_id = p.id AND wp.workspace_id = :workspace)
     ORDER BY p.title, p.id
    """
)


@dataclass(frozen=True)
class Related:
    paper_id: uuid.UUID
    title: str
    year: int | None
    hops: int  # the fewest links from the asked paper
    via: list[str]  # the kinds of link that reached it at that distance, alphabetical


@dataclass(frozen=True)
class Node:
    id: uuid.UUID
    title: str
    year: int | None
    workspaces: list[str]  # names, oldest membership first; the first one colours the node
    has_notes: bool
    status: str
    added_at: datetime  # when it came into the library (papers.created_at): the Timeline's Date added axis


@dataclass(frozen=True)
class Link:
    source: uuid.UUID
    target: uuid.UUID
    kind: str
    id: uuid.UUID | None = None  # manual links only
    label: str | None = None  # manual links only


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    links: list[Link]
    truncated: bool  # links beyond MAX_LINKS were dropped


async def related(session: AsyncSession, paper_id: uuid.UUID, hops: int = 1) -> list[Related]:
    """Library papers within `hops` links of this one, nearest first, then most kinds of link, then title. A `similar`
    link is followed for the first hop only.

    Raises InvalidInput("hops_out_of_range", allowed=[1, MAX_HOPS]), NotFound.
    """
    if not 1 <= hops <= MAX_HOPS:
        raise InvalidInput("hops_out_of_range", allowed=[1, MAX_HOPS])
    await get_paper(session, paper_id)
    rows = await session.execute(
        _RELATED, {"paper_id": paper_id, "hops": hops, **_similarity(await embedding_sources.active_name(session))}
    )
    return [Related(row.paper_id, row.title, row.year, row.hops, list(row.via)) for row in rows]


async def library_graph(session: AsyncSession, workspace_id: uuid.UUID | None = None) -> Graph:
    """Every library paper and the links between them, one per pair per kind (D109).

    `workspace_id` narrows it to that workspace's papers and the links between them. Raises NotFound for an
    unknown workspace.
    """
    if workspace_id is not None:
        await get_workspace(session, workspace_id)
    scope = {"workspace": workspace_id}
    nodes = [
        Node(row.id, row.title, row.year, list(row.workspaces), row.has_notes, row.status, row.added_at)
        for row in await session.execute(_GRAPH_NODES, scope)
    ]
    rows = list(
        await session.execute(
            _GRAPH_LINKS, {**scope, **_similarity(await embedding_sources.active_name(session)), "cap": MAX_LINKS + 1}
        )
    )
    # Nodes and links are two statements, so a paper created or deleted between them could leave a link with a missing
    # end, which the canvas's link force can't draw. Keep only links whose both ends were listed.
    listed = {node.id for node in nodes}
    links = [
        Link(row.source, row.target, row.kind, row.link_id, row.label)
        for row in rows[:MAX_LINKS]
        if row.source in listed and row.target in listed
    ]
    return Graph(nodes=nodes, links=links, truncated=len(rows) > MAX_LINKS)
