import { useSyncExternalStore } from 'react'

export type ReaderTab = 'notes' | 'chat'
export type Route = { name: 'library' } | { name: 'reader'; paperId: string; tab: ReaderTab }

const READER_HASH = /^#\/papers\/([0-9a-f-]{36})(?:\?(.*))?$/i

export function parseRoute(hash: string): Route {
  const match = READER_HASH.exec(hash)
  if (!match) return { name: 'library' }
  const tab = new URLSearchParams(match[2]).get('tab') === 'chat' ? 'chat' : 'notes'
  return { name: 'reader', paperId: match[1], tab }
}

export const readerHref = (paperId: string, tab: ReaderTab = 'notes') =>
  tab === 'notes' ? `#/papers/${paperId}` : `#/papers/${paperId}?tab=${tab}`

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// ponytail: hash routing covers two views; adopt a router once routes need more than an id.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
