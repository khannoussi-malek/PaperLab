import type { GraphLink, GraphNode } from '@/api/client'
import type { ChartTheme } from '@/features/charts/palette'

/** The switcher's tabs, in the spec's order and words (§4). */
export const VIEW_LABELS = {
  '2d': '2D',
  '3d': '3D',
  matrix: 'Matrix',
  timeline: 'Timeline',
  rings: 'Rings',
} as const

export type GraphView = keyof typeof VIEW_LABELS

export const VIEWS = Object.keys(VIEW_LABELS) as GraphView[]

/** D117: the chosen view, remembered per browser; the URL stays `#/graph`. */
export const VIEW_KEY = 'paperlab.graph.view'

type ViewStorage = Pick<Storage, 'getItem' | 'setItem'>

export const isGraphView = (value: unknown): value is GraphView => VIEWS.includes(value as GraphView)

/** The view the page opens on: the last one chosen in this browser, else 2D (also when storage is blocked). */
export function readView(storage: ViewStorage | undefined): GraphView {
  try {
    const stored = storage?.getItem(VIEW_KEY)
    return isGraphView(stored) ? stored : '2d'
  } catch {
    return '2d'
  }
}

export function writeView(storage: ViewStorage | undefined, view: GraphView): void {
  try {
    storage?.setItem(VIEW_KEY, view)
  } catch {
    // ponytail: blocked storage only loses the remembered view.
  }
}

/** D113: what every view is given. The page owns all of it, so switching views changes none of it. */
export type ViewProps = {
  nodes: GraphNode[]
  /** The visible links only: every view draws exactly what the panel lists. */
  links: GraphLink[]
  theme: ChartTheme
  colors: Map<string, string>
  /** The focused paper, when it is on screen. */
  focusId: string | null
  /** Links out (1–3). */
  hops: number
  /** The focused paper and everything within `hops` of it; null when nothing is focused, so nothing fades. */
  inFocus: Set<string> | null
  /** Focuses a paper, exactly as choosing it in the panel does. */
  onSelect: (paperId: string) => void
}
