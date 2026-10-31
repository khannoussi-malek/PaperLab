import { isConflict } from '@/api/client'

export type Settled = { status: 'saved'; eventId: string } | { status: 'noop' } | { status: 'refused' } | { status: 'failed'; error: unknown }
type Entry = { id: string; clientId: string }

/**
 * Every write goes through one promise tail, so a decide, and an undo that follows it, reach the server in the order
 * the reader acted, each only after the previous settled. No timers and no retries here: a retry is the caller
 * calling `decide` again with the same entry (same `clientId`, so a replayed reply is not a second event).
 */
export function createWriter<E extends Entry>(api: {
  post: (entry: E) => Promise<{ eventId: string }>
  undo: (eventId: string) => Promise<unknown>
}) {
  let tail: Promise<unknown> = Promise.resolve()
  const eventIds = new Map<string, string>() // clientId -> event id, read when an undo's turn comes
  const chain = <T,>(run: () => Promise<T>): Promise<T> => {
    const next = tail.then(run)
    tail = next.catch(() => undefined)
    return next
  }
  return {
    decide: (entry: E): Promise<Settled> =>
      chain(async (): Promise<Settled> => {
        try {
          const { eventId } = await api.post(entry)
          eventIds.set(entry.clientId, eventId)
          return { status: 'saved', eventId }
        } catch (error) {
          return { status: 'failed', error }
        }
      }),
    undo: (entry: E): Promise<Settled> =>
      chain(async (): Promise<Settled> => {
        const eventId = eventIds.get(entry.clientId)
        if (!eventId) return { status: 'noop' } // the decide never saved
        try {
          await api.undo(eventId)
        } catch (error) {
          // A retry after a lost reply: the server already undid it, which is what was asked for.
          if (!isConflict(error, 'already_undone'))
            return isConflict(error, 'changed_since') ? { status: 'refused' } : { status: 'failed', error }
        }
        eventIds.delete(entry.clientId)
        return { status: 'saved', eventId }
      }),
  }
}
