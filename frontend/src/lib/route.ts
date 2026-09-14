import { useSyncExternalStore } from 'react'

export type ReaderTab = 'notes' | 'chat' | 'data'
export type WorkspaceTab = 'papers' | 'notes' | 'chat'
export type Rect = [number, number, number, number]
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
  | { name: 'dataset'; datasetId: string }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HASH = /^#\/(papers|workspaces)\/([0-9a-f-]{36})(?:\?(.*))?$/i
const CHARTS_HASH = /^#\/charts(?:\/(new|[0-9a-f-]{36})(\/edit)?)?(?:\?(.*))?$/i
const DATASET_HASH = /^#\/datasets\/([0-9a-f-]{36})$/i

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
  const charts = CHARTS_HASH.exec(hash)
  if (charts) return chartsRoute(charts)
  const dataset = DATASET_HASH.exec(hash)
  if (dataset) return UUID.test(dataset[1]) ? { name: 'dataset', datasetId: dataset[1] } : { name: 'library' }
  const match = HASH.exec(hash)
  if (!match || !UUID.test(match[2])) return { name: 'library' }
  const params = new URLSearchParams(match[3])
  const tab = params.get('tab')
  if (match[1] === 'workspaces') {
    return { name: 'workspace', workspaceId: match[2], tab: tab === 'notes' || tab === 'chat' ? tab : 'papers' }
  }
  const readerTab = tab === 'chat' || tab === 'data' ? tab : 'notes'
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

export const chartsHref = '#/charts'
export const chartHref = (chartId: string) => `#/charts/${chartId}`
export const editChartHref = (chartId: string) => `#/charts/${chartId}/edit`
/** With a dataset, the builder starts from a quick chart of it. */
export const newChartHref = (datasetId?: string) => (datasetId ? `#/charts/new?dataset=${datasetId}` : '#/charts/new')
export const datasetHref = (datasetId: string) => `#/datasets/${datasetId}`

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// ponytail: hash routing covers these views with a few params; adopt a router once routes nest.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
