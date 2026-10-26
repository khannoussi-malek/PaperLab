import { useSyncExternalStore } from 'react'

/**
 * Text a file's pane could not save when it closed. `base` is the file's updated_at the text was edited against, so
 * reopening can tell whether the server moved on meanwhile.
 */
export type KeptText = { text: string; reason: 'conflict' | 'error'; base: string | null }

// Module-level, so the text outlives the page: leaving for the Library or another manuscript, the route remounting and
// the error boundary's Try again all keep it. Gone with the tab (a reload gets the browser's leave prompt instead).
const entries = new Map<string, KeptText>()
const listeners = new Set<() => void>()
let version = 0
const views = new Map<string, { version: number; value: Record<string, KeptText> }>()

const keyOf = (manuscriptId: string, path: string) => `${manuscriptId}\u0000${path}`
const changed = () => {
  version += 1
  listeners.forEach((l) => l())
}

export const keptTexts = {
  get: (manuscriptId: string, path: string) => entries.get(keyOf(manuscriptId, path)),
  set(manuscriptId: string, path: string, kept: KeptText) {
    entries.set(keyOf(manuscriptId, path), kept)
    changed()
  },
  remove(manuscriptId: string, path: string) {
    if (entries.delete(keyOf(manuscriptId, path))) changed()
  },
  clear() {
    entries.clear()
    changed()
  },
  count: () => entries.size,
  /** This manuscript's kept texts by path. The same object until something changes, so it suits useSyncExternalStore. */
  forManuscript(manuscriptId: string): Record<string, KeptText> {
    const cached = views.get(manuscriptId)
    if (cached?.version === version) return cached.value
    const prefix = `${manuscriptId}\u0000`
    const value = Object.fromEntries([...entries].filter(([k]) => k.startsWith(prefix)).map(([k, v]) => [k.slice(prefix.length), v]))
    views.set(manuscriptId, { version, value })
    return value
  },
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => void listeners.delete(listener)
  },
}

export const useKeptTexts = (manuscriptId: string) =>
  useSyncExternalStore(keptTexts.subscribe, () => keptTexts.forManuscript(manuscriptId))

export const useKeptCount = () => useSyncExternalStore(keptTexts.subscribe, keptTexts.count)
