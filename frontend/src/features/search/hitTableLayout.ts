import type { Hit } from '@/entities'
import type { PanelLimits } from '@/components/panelWidth'
import type { HitSort } from '@/features/search/hitSort'

export const ROW_HEIGHT = 44
// Below `sm` (M71) a row is at least two lines: the title alone on the first, its chips and actions below.
export const ROW_HEIGHT_NARROW = 72
export const NARROW = '(max-width: 639px)'
export const NO_IMPORT_REASON = 'No relevant results waiting to be imported'
/** `AppShell`'s `p-3` on the view pane, between the preview's right edge and the window's. */
export const PANE_PADDING_PX = 12

/** The hit preview column: 352px was the old fixed 22rem. Half the window at most, so the hit list keeps the larger part. */
export const HIT_PREVIEW: PanelLimits = {
  storageKey: 'paperlab-hit-preview-width',
  defaultWidth: 352,
  minWidth: 280,
  maxShare: 0.5,
}

export function hasPdfOrAbstract(hit: Hit): boolean {
  return hit.acquisition_status === 'imported' || hit.acquisition_status === 'manual' || Boolean(hit.abstract)
}

// A hit with an abstract to read or a PDF already in the corpus is the one worth looking at first — a bare
// title with neither is the hardest to judge relevance from. Stable sort (native since ES2019), so hits within
// each group keep their existing (first_seen_at, id) order from the server. Ranked order is already sorted by
// the server (most likely relevant first) and must stay that way — sorting it again here would undo the point.
// ponytail: "year" sorts only the already-loaded found-order page(s) client-side, same data source as found
// order (no new endpoint) — a hit with no year sorts last. Rows already on screen can shift as more pages load
// in behind them; fine for this quick screening-helper view, upgrade to a server-sorted endpoint (like ranked)
// if that ever matters.
export function sortVisibleRows(sort: HitSort, filteredRows: Hit[]): Hit[] {
  return sort === 'ranked'
    ? filteredRows
    : sort === 'ai'
      ? filteredRows // the server already ordered these by score
      : sort === 'year'
      ? filteredRows.slice().sort((a, b) => (b.year ?? -Infinity) - (a.year ?? -Infinity))
      : filteredRows.slice().sort((a, b) => Number(hasPdfOrAbstract(b)) - Number(hasPdfOrAbstract(a)))
}
