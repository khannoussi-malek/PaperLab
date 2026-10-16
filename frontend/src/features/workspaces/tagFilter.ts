import type { Paper } from '../../api/client'
import type { TagMatch } from '../../lib/route'

/** Keeps the papers carrying any/all of the selected tags. Selected tags no paper carries (renamed or deleted) are
 * ignored, so a stale URL never empties the list; with none left, everything shows. */
export function filterByTags(papers: Paper[], map: Record<string, string[]>, tags: string[], match: TagMatch): Paper[] {
  const existing = new Set(Object.values(map).flat())
  const wanted = tags.filter((t) => existing.has(t))
  if (!wanted.length) return papers
  return papers.filter((p) => {
    const names = map[p.id] ?? []
    return match === 'all' ? wanted.every((t) => names.includes(t)) : wanted.some((t) => names.includes(t))
  })
}
