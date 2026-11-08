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
}
export type Edge = { from: string; to: string; kind: string; dashed: boolean }
export type Layout = { boxes: Box[]; edges: Edge[]; width: number; height: number }

/** Each child's drawn link: earliest `created_at`, then the root listed first, then the parent id. */
export function primaryParent(links: ProvLink[], roots: ProvRoot[] = []): Map<string, ProvLink> {
  const rank = (l: ProvLink) => {
    const i = roots.findIndex((r) => r.id === l.parent)
    return i < 0 ? roots.length : i
  }
  const before = (a: ProvLink, b: ProvLink) =>
    (a.created_at ?? '').localeCompare(b.created_at ?? '') || rank(a) - rank(b) || a.parent.localeCompare(b.parent)
  const best = new Map<string, ProvLink>()
  for (const l of links) {
    const cur = best.get(l.child)
    if (!cur || before(l, cur) < 0) best.set(l.child, l)
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
  const primary = primaryParent(links, roots)
  const incoming = new Map<string, number>()
  for (const l of links) incoming.set(l.child, (incoming.get(l.child) ?? 0) + 1)

  const children = new Map<string, string[]>()
  for (const [child, l] of primary) {
    if (!byId.has(child)) continue
    children.set(l.parent, [...(children.get(l.parent) ?? []), child])
  }

  // Reachable-from-a-root tree (a parent cycle with no root is never drawn), minus folded subtrees.
  const seen = new Set<string>()
  const shown = (id: string): string[] =>
    folded.has(id) ? [] : (children.get(id) ?? []).filter((c) => !seen.has(c) && seen.add(c))
  // Keep a node when it matches the filter or has a kept descendant (then it is drawn faded).
  const keep = new Map<string, boolean>()
  const visit = (id: string): boolean => {
    const own = !hidden.has(id)
    const kids = shown(id).map(visit).filter(Boolean).length > 0
    keep.set(id, own || kids)
    return own || kids
  }
  roots.forEach((r) => (seen.add(r.id), keep.set(r.id, true), shown(r.id).forEach(visit)))

  const boxes: Box[] = []
  const edges: Edge[] = []
  let leaf = 0
  const place = (id: string, col: number): number => {
    const kids = (children.get(id) ?? []).filter((c) => keep.get(c) && !folded.has(id))
    const ys = kids.map((k) => place(k, (byId.get(k)?.level ?? col) + 1))
    const y = ys.length ? (ys[0] + ys[ys.length - 1]) / 2 : leaf++ * ROW
    const node = byId.get(id) ?? null
    const root = roots.find((r) => r.id === id) ?? null
    boxes.push({
      id, x: col * COL, y, node, root,
      faded: node ? hidden.has(id) : hidden.size > 0,
      extraPaths: node ? Math.max(0, (incoming.get(id) ?? 1) - 1) : 0,
    })
    kids.forEach((k) => {
      const l = primary.get(k)!
      edges.push({ from: id, to: k, kind: l.kind, dashed: l.kind === 'cited_by' })
    })
    return y
  }
  roots.forEach((r) => place(r.id, 0))

  const width = Math.max(0, ...boxes.map((b) => b.x)) + BOX_W
  return { boxes, edges, width, height: Math.max(leaf, 1) * ROW }
}
