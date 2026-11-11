import { useEffect, useSyncExternalStore } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { sileo } from 'sileo'
import { useUpdateManuscript } from '@/api/queries'

export type Ticks = Record<string, unknown>
type Store = { shown: Ticks; server: Ticks; pending: number; listeners: Set<() => void> }

// One store per query client and manuscript, shared by the final-steps and guideline panels, so every patch is built from the same current dict.
const stores = new WeakMap<QueryClient, Map<string, Store>>()

function storeFor(client: QueryClient, id: string, initial: Ticks): Store {
  const byId = stores.get(client) ?? new Map<string, Store>()
  stores.set(client, byId)
  const found = byId.get(id)
  if (found) return found
  const made: Store = { shown: initial, server: initial, pending: 0, listeners: new Set() }
  byId.set(id, made)
  return made
}

const notify = (s: Store) => s.listeners.forEach((l) => l())

/** `shown` is what the boxes display; `send(next)` ticks optimistically and reverts to the last server value if the save fails. */
export function useChecklist(manuscriptId: string, checklist: Ticks) {
  const client = useQueryClient()
  const update = useUpdateManuscript()
  const store = storeFor(client, manuscriptId, checklist)
  const shown = useSyncExternalStore(
    (l) => {
      store.listeners.add(l)
      return () => store.listeners.delete(l)
    },
    () => store.shown,
  )
  // A prop that arrives while a save is pending may be older than that save, so it is ignored until the saves settle.
  useEffect(() => {
    if (store.pending > 0) return
    store.server = checklist
    if (store.shown !== checklist) {
      store.shown = checklist
      notify(store)
    }
  }, [store, checklist])

  const send = async (next: Ticks) => {
    store.shown = next
    store.pending += 1
    notify(store)
    try {
      await update.mutateAsync({ id: manuscriptId, patch: { checklist: next } })
      store.server = next
    } catch {
      store.shown = store.server
      sileo.error({ title: "Couldn't save the checklist" })
    } finally {
      store.pending -= 1
      notify(store)
    }
  }
  // Read at click time, not render time.
  const current = () => store.shown
  return { shown, current, send }
}
