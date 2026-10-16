import type { Paper, TagSummary } from '../../api/client'
import type { TagMatch } from '../../lib/route'

/** `known` is every existing tag name (a tag with no papers is still known). Keeps the papers carrying any/all of the selected tags. Selected tags no paper carries (renamed or deleted) are
 * ignored, so a stale URL never empties the list; with none left, everything shows. */
export function filterByTags(
  papers: Paper[],
  map: Record<string, string[]>,
  tags: string[],
  match: TagMatch,
  known: string[],
): Paper[] {
  const existing = new Set(known)
  const wanted = tags.filter((t) => existing.has(t))
  if (!wanted.length) return papers
  return papers.filter((p) => {
    const names = map[p.id] ?? []
    return match === 'all' ? wanted.every((t) => names.includes(t)) : wanted.some((t) => names.includes(t))
  })
}

export const toggled = (selected: string[], name: string) =>
  selected.includes(name) ? selected.filter((t) => t !== name) : [...selected, name]

export const coverageText = (t: TagSummary) =>
  `${t.papers} papers · ${t.peer_reviewed} peer-reviewed, ${t.preprint} preprints, ${t.unknown_review} unknown · ` +
  `${t.full_text} full text, ${t.abstract} abstract only, ${t.metadata} metadata only`
