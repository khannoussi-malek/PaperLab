import type { ProvLink, ProvNode, ProvRoot } from '@/api/client'

export const COL = 180
export const ROW = 40
export const BOX_W = 150
export const BOX_H = 30

export type Box = {
  id: string
  x: number
  y: number
  /** Null for a search-root box. */
  node: ProvNode | null
  root: ProvRoot | null
  faded: boolean
  /** Incoming links beyond the one this box is drawn under. */
  extraPaths: number
  /** For a folded box under a filter: matching papers hidden inside it. */
  foldedMatches: number
}
export type Edge = { from: string; to: string; kind: string; dashed: boolean }
export type Layout = { boxes: Box[]; edges: Edge[]; width: number; height: number }

export const isUnknown = (id: string) => id.endsWith(':unknown')
export const PARENT_NOT_RECORDED = 'Parent not recorded'
const isRootType = (id: string) => id.startsWith('root:') || isUnknown(id)

/**
 * Each child's drawn link, matching the backend's `_tree_roots`: only a parent one level up counts (for level 0, only
 * a root), then earliest `created_at`, then the root listed first, then the parent id. Every other link is an extra path.
 */
export function primaryParent(links: ProvLink[], roots: ProvRoot[] = [], nodes: ProvNode[] = []): Map<string, ProvLink> {
  const level = new Map(nodes.map((n) => [n.id, n.level]))
  const rank = (l: ProvLink) => {
    const i = roots.findIndex((r) => r.id === l.parent)
    return i < 0 ? roots.length : i
  }
  const before = (a: ProvLink, b: ProvLink) =>
    (a.created_at ?? '').localeCompare(b.created_at ?? '') || rank(a) - rank(b) || a.parent.localeCompare(b.parent)
  const byChild = new Map<string, ProvLink[]>()
  for (const l of links) {
    const list = byChild.get(l.child)
    if (list) list.push(l)
    else byChild.set(l.child, [l])
  }
  const best = new Map<string, ProvLink>()
  for (const [child, all] of byChild) {
    const lv = level.get(child)
    const fits = lv === undefined ? all : all.filter((l) => (lv === 0 ? isRootType(l.parent) : level.get(l.parent) === lv - 1))
    const pool = fits.length ? fits : all // ponytail: a link that fits no level rule still draws rather than vanishing
    best.set(child, pool.reduce((a, b) => (before(b, a) < 0 ? b : a)))
  }
  return best
}

/** Left-to-right tidy tree: x is the level column, y the leaf order with parents centred on their children. */
export function tidyLayout(
  nodes: ProvNode[],
  links: ProvLink[],
  roots: ProvRoot[],
  folded: Set<string>,
  hidden: Set<string>,
): Layout {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const primary = primaryParent(links, roots, nodes)
  const incoming = new Map<string, number>()
  for (const l of links) incoming.set(l.child, (incoming.get(l.child) ?? 0) + 1)

  const children = new Map<string, string[]>()
  for (const [child, l] of primary) {
    if (!byId.has(child)) continue
    const list = children.get(l.parent)
    if (list) list.push(child)
    else children.set(l.parent, [child])
  }

  const topIds = [...roots.map((r) => r.id), ...nodes.filter((n) => isUnknown(n.id)).map((n) => n.id)]
  // Keep a node when it matches the filter or has a kept descendant (then it is drawn faded). Folding does not
  // stop this walk, so a folded node still knows how many matches it hides.
  const seen = new Set<string>(topIds)
  const keep = new Map<string, boolean>()
  const matches = new Map<string, number>() // matching descendants, not counting the node itself
  const walk = (id: string): number => {
    let below = 0
    let kept = false
    for (const c of children.get(id) ?? []) {
      if (seen.has(c)) continue
      seen.add(c)
      below += walk(c)
      kept = kept || keep.get(c)!
    }
    matches.set(id, below)
    const own = byId.has(id) && !hidden.has(id)
    keep.set(id, own || kept || !byId.has(id))
    return below + (own ? 1 : 0)
  }
  topIds.forEach(walk)

  const boxes: Box[] = []
  const edges: Edge[] = []
  let leaf = 0
  const place = (id: string, col: number): number => {
    const kids = folded.has(id) ? [] : (children.get(id) ?? []).filter((c) => keep.get(c))
    const slot = boxes.length // a box goes in before its children, so DOM and tab order run roots -> leaves
    boxes.push(undefined as unknown as Box)
    const ys = kids.map((k) => place(k, (byId.get(k)?.level ?? col) + 1))
    const y = ys.length ? (ys[0] + ys[ys.length - 1]) / 2 : leaf++ * ROW
    const node = byId.get(id) ?? null
    const root = roots.find((r) => r.id === id) ?? null
    boxes[slot] = {
      id, x: col * COL, y, node, root,
      faded: node ? hidden.has(id) : hidden.size > 0 && (matches.get(id) ?? 0) === 0,
      extraPaths: node && !isUnknown(id) ? Math.max(0, (incoming.get(id) ?? 1) - 1) : 0,
      foldedMatches: folded.has(id) && hidden.size > 0 ? (matches.get(id) ?? 0) : 0,
    }
    kids.forEach((k) => {
      const l = primary.get(k)!
      edges.push({ from: id, to: k, kind: l.kind, dashed: l.kind === 'cited_by' })
    })
    return y
  }
  // "Parent not recorded" boxes stand in for a search, but their children are one level up: column 1, under the Level 0 header.
  topIds.forEach((id) => place(id, isUnknown(id) ? 1 : 0))

  const width = Math.max(0, ...boxes.map((b) => b.x)) + BOX_W
  return { boxes, edges, width, height: Math.max(leaf, 1) * ROW }
}
