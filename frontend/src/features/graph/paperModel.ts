import type { GraphLink } from '@/api/client'
import { endId } from './graphModel'

// What the 3D view makes stand out, so the owner always knows which paper they are looking at: the selected paper
// glows brightest and is named, the papers it links to directly glow softer and are named too, the rest fade.

export type Emphasis = 'selected' | 'connected' | 'faded' | 'plain'

export function emphasis(id: string, focusId: string | null, inFocus: Set<string> | null): Emphasis {
  if (focusId === null || inFocus === null) return 'plain'
  if (id === focusId) return 'selected'
  return inFocus.has(id) ? 'connected' : 'faded'
}

/** How many papers carry a name at once, the selected one included: more and the names cover each other. */
export const LABEL_CAP = 10

/** The selected paper and the papers it links to directly (either way), up to LABEL_CAP. */
export function labelledIds(links: GraphLink[], focusId: string | null): Set<string> {
  const ids = new Set<string>()
  if (focusId === null) return ids
  ids.add(focusId)
  for (const link of links) {
    if (ids.size >= LABEL_CAP) break
    const [a, b] = [endId(link.source), endId(link.target)]
    if (a === focusId) ids.add(b)
    else if (b === focusId) ids.add(a)
  }
  return ids
}

const TITLE_MAX = 42

/** A title short enough for a label over a paper, cut at a word. */
export function shortTitle(title: string): string {
  if (title.length <= TITLE_MAX) return title
  const cut = title.slice(0, TITLE_MAX)
  const space = cut.lastIndexOf(' ')
  return `${(space > 20 ? cut.slice(0, space) : cut).replace(/[\s,:;.-]+$/, '')}…`
}

export type LinkState = 'active' | 'plain' | 'faded'
type Ends = { source: string | { id: string }; target: string | { id: string } }

/** A link of the selected paper is active (drawn thick and gold); one leaving the focus fades; the rest stay plain. */
export function linkState(link: Ends, focusId: string | null, inFocus: Set<string> | null): LinkState {
  if (focusId === null || inFocus === null) return 'plain'
  const [a, b] = [endId(link.source), endId(link.target)]
  if (a === focusId || b === focusId) return 'active'
  return inFocus.has(a) && inFocus.has(b) ? 'plain' : 'faded'
}
