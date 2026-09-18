import { useSyncExternalStore } from 'react'
import { withViewTransition } from '@/components/motion'

export type ReaderTab = 'notes' | 'chat' | 'data' | 'similar' | 'references'
export type WorkspaceTab = 'papers' | 'notes' | 'chat'
export type Rect = [number, number, number, number]
/** A grid cell to scroll to and focus once, when a chart point of data typed in is opened. */
export type CellFocus = { rowId: string; columnId: string }
/** What the reader shows once on load, then drops from the hash. `id` tells one target from the next. */
export type ReaderTarget =
  | { kind: 'chunk'; id: string; page: number }
  | { kind: 'note'; id: string }
  | { kind: 'region'; id: string; page: number; rects: Rect[] }
  | null
export type Route =
  | { name: 'library' }
  | { name: 'reader'; paperId: string; tab: ReaderTab; target: ReaderTarget }
  | { name: 'workspace'; workspaceId: string; tab: WorkspaceTab }
  | { name: 'charts' }
  | { name: 'chart'; chartId: string }
  | { name: 'chart-builder'; chartId: string | null; datasetId: string | null }
  | { name: 'dataset'; datasetId: string; focus: CellFocus | null }
  | { name: 'settings' }
  | { name: 'connect-claude' }
  | { name: 'graph' }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HASH = /^#\/(papers|workspaces)\/([0-9a-f-]{36})(?:\?(.*))?$/i
const CHARTS_HASH = /^#\/charts(?:\/(new|[0-9a-f-]{36})(\/edit)?)?(?:\?(.*))?$/i
const DATASET_HASH = /^#\/datasets\/([0-9a-f-]{36})(?:\?(.*))?$/i
const SETTINGS_HASH = '#/settings'
const CONNECT_CLAUDE_HASH = '#/connect-claude'
const GRAPH_HASH = '#/graph'

function pageOf(params: URLSearchParams): number | null {
  const page = Number(params.get('page'))
  return Number.isInteger(page) && page >= 1 ? page : null
}

function rectsOf(text: string | null): Rect[] | null {
  if (!text) return null
  const rects = text.split(';').map((part) => part.split(',').map(Number))
  return rects.every((r) => r.length === 4 && r.every(Number.isFinite)) ? (rects as Rect[]) : null
}

function readerTarget(params: URLSearchParams): ReaderTarget {
  const page = pageOf(params)
  const chunk = params.get('chunk') ?? ''
  if (UUID.test(chunk) && page !== null) return { kind: 'chunk', id: chunk, page }
  const note = params.get('note') ?? ''
  if (UUID.test(note)) return { kind: 'note', id: note }
  const rects = rectsOf(params.get('rects'))
  return rects && page !== null ? { kind: 'region', id: `${page}:${params.get('rects')}`, page, rects } : null
}

function chartsRoute(match: RegExpExecArray): Route {
  const [, target, edit, query] = match
  if (target === undefined) return { name: 'charts' }
  if (target.toLowerCase() === 'new') {
    const dataset = new URLSearchParams(query).get('dataset') ?? ''
    return { name: 'chart-builder', chartId: null, datasetId: UUID.test(dataset) ? dataset : null }
  }
  if (!UUID.test(target)) return { name: 'library' }
  return edit ? { name: 'chart-builder', chartId: target, datasetId: null } : { name: 'chart', chartId: target }
}

export function parseRoute(hash: string): Route {
  if (hash === SETTINGS_HASH) return { name: 'settings' }
  if (hash === CONNECT_CLAUDE_HASH) return { name: 'connect-claude' }
  if (hash === GRAPH_HASH) return { name: 'graph' }
  const charts = CHARTS_HASH.exec(hash)
  if (charts) return chartsRoute(charts)
  const dataset = DATASET_HASH.exec(hash)
  if (dataset) {
    if (!UUID.test(dataset[1])) return { name: 'library' }
    const params = new URLSearchParams(dataset[2])
    const [rowId, columnId] = [params.get('row') ?? '', params.get('column') ?? '']
    const focus = UUID.test(rowId) && UUID.test(columnId) ? { rowId, columnId } : null
    return { name: 'dataset', datasetId: dataset[1], focus }
  }
  const match = HASH.exec(hash)
  if (!match || !UUID.test(match[2])) return { name: 'library' }
  const params = new URLSearchParams(match[3])
  const tab = params.get('tab')
  if (match[1] === 'workspaces') {
    return { name: 'workspace', workspaceId: match[2], tab: tab === 'notes' || tab === 'chat' ? tab : 'papers' }
  }
  const readerTab = tab === 'chat' || tab === 'data' || tab === 'similar' || tab === 'references' ? tab : 'notes'
  return { name: 'reader', paperId: match[2], tab: readerTab, target: readerTarget(params) }
}

export const readerHref = (paperId: string, tab: ReaderTab = 'notes') =>
  tab === 'notes' ? `#/papers/${paperId}` : `#/papers/${paperId}?tab=${tab}`

/** The page travels with the chunk, so the reader fetches only that page's chunks to find its rects. */
export const chunkHref = (paperId: string, chunkId: string, page: number) =>
  `#/papers/${paperId}?chunk=${chunkId}&page=${page}`

export const noteHref = (paperId: string, noteId: string) => `#/papers/${paperId}?note=${noteId}`

/** A place on a page to flash, on the Data tab: where a charted number or a captured table sits. */
export const regionHref = (paperId: string, page: number, rects: Rect[]) =>
  `#/papers/${paperId}?tab=data&page=${page}&rects=${rects.map((r) => r.join(',')).join(';')}`

export const workspaceHref = (workspaceId: string, tab: WorkspaceTab = 'papers') =>
  tab === 'papers' ? `#/workspaces/${workspaceId}` : `#/workspaces/${workspaceId}?tab=${tab}`

export const settingsHref = SETTINGS_HASH
export const connectClaudeHref = CONNECT_CLAUDE_HASH
export const graphHref = GRAPH_HASH
export const chartsHref = '#/charts'
export const chartHref = (chartId: string) => `#/charts/${chartId}`
export const editChartHref = (chartId: string) => `#/charts/${chartId}/edit`
/** With a dataset, the builder starts from a quick chart of it. */
export const newChartHref = (datasetId?: string) => (datasetId ? `#/charts/new?dataset=${datasetId}` : '#/charts/new')
export const datasetHref = (datasetId: string, focus?: CellFocus) =>
  focus ? `#/datasets/${datasetId}?row=${focus.rowId}&column=${focus.columnId}` : `#/datasets/${datasetId}`

/** Whether two URLs show the same page: only the query (a tab, a target) differs, so the view needs no cross-fade. */
export const samePage = (oldURL: string, newURL: string) => new URL(oldURL).hash.split('?')[0] === new URL(newURL).hash.split('?')[0]

// One hashchange listener for every useRoute, so a navigation is one cross-fade however many components read the route.
// A new page cross-fades; a tab or a target within one swaps at once, since its panel fades in by itself and the page
// takes no clicks while a transition runs.
// ponytail: the snapshot reads the live hash, so a render that lands before the transition's update shows the new page
// early and that navigation skips its fade; hold the hash in the store if that ever shows.
const listeners = new Set<() => void>()
function notifyAll(event: HashChangeEvent) {
  const notify = () => listeners.forEach((listener) => listener())
  if (samePage(event.oldURL, event.newURL)) notify()
  else withViewTransition(notify)
}

function subscribe(onChange: () => void) {
  if (listeners.size === 0) window.addEventListener('hashchange', notifyAll)
  listeners.add(onChange)
  return () => {
    listeners.delete(onChange)
    if (listeners.size === 0) window.removeEventListener('hashchange', notifyAll)
  }
}

// ponytail: hash routing covers these views with a few params; adopt a router once routes nest.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
