import { useSyncExternalStore } from 'react'

export type ReaderTab = 'notes' | 'chat'
export type WorkspaceTab = 'papers' | 'notes' | 'chat'
/** What the reader shows once on load, then drops from the hash. */
export type ReaderTarget = { kind: 'chunk'; id: string; page: number } | { kind: 'note'; id: string } | null
export type Route =
  | { name: 'library' }
  | { name: 'reader'; paperId: string; tab: ReaderTab; target: ReaderTarget }
  | { name: 'workspace'; workspaceId: string; tab: WorkspaceTab }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HASH = /^#\/(papers|workspaces)\/([0-9a-f-]{36})(?:\?(.*))?$/i

function readerTarget(params: URLSearchParams): ReaderTarget {
  const chunk = params.get('chunk') ?? ''
  const page = Number(params.get('page'))
  if (UUID.test(chunk) && Number.isInteger(page) && page >= 1) return { kind: 'chunk', id: chunk, page }
  const note = params.get('note') ?? ''
  return UUID.test(note) ? { kind: 'note', id: note } : null
}

export function parseRoute(hash: string): Route {
  const match = HASH.exec(hash)
  if (!match || !UUID.test(match[2])) return { name: 'library' }
  const params = new URLSearchParams(match[3])
  const tab = params.get('tab')
  if (match[1] === 'workspaces') {
    return { name: 'workspace', workspaceId: match[2], tab: tab === 'notes' || tab === 'chat' ? tab : 'papers' }
  }
  return { name: 'reader', paperId: match[2], tab: tab === 'chat' ? 'chat' : 'notes', target: readerTarget(params) }
}

export const readerHref = (paperId: string, tab: ReaderTab = 'notes') =>
  tab === 'notes' ? `#/papers/${paperId}` : `#/papers/${paperId}?tab=${tab}`

/** The page travels with the chunk, so the reader fetches only that page's chunks to find its rects. */
export const chunkHref = (paperId: string, chunkId: string, page: number) =>
  `#/papers/${paperId}?chunk=${chunkId}&page=${page}`

export const noteHref = (paperId: string, noteId: string) => `#/papers/${paperId}?note=${noteId}`

export const workspaceHref = (workspaceId: string, tab: WorkspaceTab = 'papers') =>
  tab === 'papers' ? `#/workspaces/${workspaceId}` : `#/workspaces/${workspaceId}?tab=${tab}`

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// ponytail: hash routing covers three views with a few params; adopt a router once routes nest.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
