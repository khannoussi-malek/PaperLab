import { useSyncExternalStore } from 'react'

export type Route = { name: 'library' } | { name: 'reader'; paperId: string }

const READER_HASH = /^#\/papers\/([0-9a-f-]{36})$/i

export function parseRoute(hash: string): Route {
  const match = READER_HASH.exec(hash)
  return match ? { name: 'reader', paperId: match[1] } : { name: 'library' }
}

export const readerHref = (paperId: string) => `#/papers/${paperId}`

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// ponytail: hash routing covers two views; adopt a router once routes need more than an id.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
