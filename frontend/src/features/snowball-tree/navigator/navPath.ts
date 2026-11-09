import type { ProvenanceOut } from '@/api/client'
import { isUnknown, primaryParent } from '../layout'

export type NavEntry = { id: string; via: 'search' | 'cites' | 'cited_by' | 'hand' }

export const viaOf = (kind: string): NavEntry['via'] => (kind === 'cites' || kind === 'cited_by' ? kind : 'search')
const SEP = ','

/** The walk from a search down to `nodeId`, by the tree's own primary-parent rule. Empty when the paper isn't in the data. */
export function primaryPath(data: ProvenanceOut, nodeId: string): NavEntry[] {
  const parents = primaryParent(data.links, data.roots, data.nodes)
  const out: NavEntry[] = []
  const seen = new Set<string>()
  for (let id = nodeId, link = parents.get(id); link && !seen.has(id); link = parents.get(id)) {
    seen.add(id)
    out.unshift({ id, via: viaOf(link.kind) })
    id = link.parent
  }
  if (out.length === 0) {
    if (!data.nodes.some((n) => n.id === nodeId)) return []
    const self: NavEntry = { id: nodeId, via: 'search' }
    return nodeId.startsWith('paper:') ? [{ id: 'root:hand', via: 'hand' }, self] : [self]
  }
  const rootId = parents.get(out[0].id)!.parent
  return [{ id: rootId, via: rootId === 'root:hand' ? 'hand' : 'search' }, ...out]
}

export const toParam = (path: NavEntry[]): string => path.map((e) => e.id).join(SEP)

/** Reads `nav=` back into a path, cutting at the first id that is gone or no longer a child of the one before. */
export function parseNav(param: string, data: ProvenanceOut): { path: NavEntry[]; cut: boolean } {
  const ids = param.split(SEP).filter(Boolean)
  const parents = primaryParent(data.links, data.roots, data.nodes)
  const path: NavEntry[] = []
  for (const id of ids) {
    const prev = path[path.length - 1]
    if (!prev) {
      const isRoot = id === 'root:hand' || (id.startsWith('root:') && (data.roots.some((r) => r.id === id) || data.links.some((l) => l.parent === id)))
      if (!isRoot && !(isUnknown(id) && data.nodes.some((n) => n.id === id))) break
      path.push({ id, via: id === 'root:hand' ? 'hand' : 'search' })
      continue
    }
    const main = parents.get(id)
    const link = main?.parent === prev.id ? main : data.links.find((l) => l.parent === prev.id && l.child === id)
    const handPaper = prev.id === 'root:hand' && id.startsWith('paper:') // a library paper added by hand may have no tree node; the card reads it from the library
    if (!link && !handPaper) break
    path.push({ id, via: link ? viaOf(link.kind) : 'search' })
  }
  return { path, cut: path.length < ids.length }
}

/** What the breadcrumb draws: the whole path up to `max` entries, else the first, a gap, and the last two. */
export function collapse(path: NavEntry[], max = 4): Array<NavEntry | 'more'> {
  return path.length <= max ? path : [path[0], 'more', ...path.slice(-2)]
}
