import { useSyncExternalStore } from 'react'

/**
 * Text a file's pane could not save when it closed. `base` is the file's updated_at the text was edited against, so
 * reopening can tell whether the server moved on meanwhile. `seq` is the closing pane's mount number; `id` is
 * `${path}#${seq}`, so each pane's copy is its own entry and two panes on one file never overwrite each other.
 */
export type KeptText = { id: string; path: string; text: string; reason: 'conflict' | 'error'; base: string | null; seq: number }

// Module-level, so the text outlives the page: leaving for the Library or another manuscript, the route remounting and
// the error boundary's Try again all keep it. Gone with the tab (a reload gets the browser's leave prompt instead).
const entries = new Map<string, KeptText & { manuscriptId: string }>()
const listeners = new Set<() => void>()
let version = 0
let seqCounter = 0
let flushing = 0 // unmount saves still in flight: their text may yet become an entry
const views = new Map<string, { version: number; value: KeptText[] }>()

const changed = () => {
  version += 1
  listeners.forEach((l) => l())
}

export const keptTexts = {
  /**
   * Keeps a closing pane's text as its own entry and returns its id. It replaces only `replaces` (the entries that pane
   * took over, whose text is in this one) and that pane's own earlier write; every other entry stays.
   */
  put(manuscriptId: string, kept: Omit<KeptText, 'id'>, replaces: readonly string[] = []): string {
    const id = `${kept.path}#${kept.seq}`
    replaces.forEach((r) => entries.delete(r))
    entries.set(id, { ...kept, id, manuscriptId })
    changed()
    return id
  },
  nextSeq: () => (seqCounter += 1),
  flushStarted() {
    flushing += 1
    changed()
  },
  flushSettled() {
    flushing -= 1
    changed()
  },
  /** Drops exactly this entry. */
  remove(id: string) {
    if (entries.delete(id)) changed()
  },
  clear() {
    entries.clear()
    flushing = 0
    changed()
  },
  /** Kept entries plus saves in flight: what would be lost if the tab closed now. */
  count: () => entries.size + flushing,
  /** This manuscript's kept texts, oldest first. The same array until something changes, so it suits useSyncExternalStore. */
  forManuscript(manuscriptId: string): KeptText[] {
    const cached = views.get(manuscriptId)
    if (cached?.version === version) return cached.value
    const value = [...entries.values()].filter((k) => k.manuscriptId === manuscriptId).map(({ manuscriptId: _, ...k }) => k)
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
