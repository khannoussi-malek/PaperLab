export type SaveState = 'saved' | 'saving' | 'unsaved' | 'conflict'

type Options = {
  delayMs: number
  /** How long after a failed save (not a conflict) to try again. */
  retryMs?: number
  /** Resolves `{ conflict: true }` when the file changed elsewhere; a rejection leaves the text unsaved. */
  save: (text: string) => Promise<{ conflict: boolean } | void>
  onState?: (state: SaveState) => void
  onError?: (error: Error) => void
}

/**
 * Saves the latest text `delayMs` after the last change, one save at a time. The text stays in `unsavedText` until a
 * save succeeds, so a failure or a conflict never loses it; a conflict stops saving until the user picks a side
 * (`keepMine` or `reload`), and a plain failure retries after `retryMs`.
 */
export function createAutosave({ delayMs, retryMs = 5000, save, onState, onError }: Options) {
  let state: SaveState = 'saved'
  let pending: string | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let queue: Promise<void> = Promise.resolve()
  let disposed = false

  const setState = (next: SaveState) => {
    state = next
    onState?.(next)
  }

  async function run() {
    if (state === 'conflict' || pending === null) return
    const text = pending
    setState('saving')
    try {
      const result = await save(text)
      if (result?.conflict) return setState('conflict')
      if (pending === text) pending = null
      setState(pending === null ? 'saved' : 'unsaved')
    } catch (error) {
      setState('unsaved')
      onError?.(error instanceof Error ? error : new Error(String(error)))
      if (!disposed) timer = setTimeout(() => void flush(), retryMs)
    }
  }

  function flush() {
    clearTimeout(timer)
    queue = queue.then(run)
    return queue
  }

  return {
    get state() {
      return state
    },
    /** The text that has not reached the server, if any. */
    get unsavedText() {
      return pending
    },
    change(text: string) {
      pending = text
      if (state === 'conflict') return
      setState('unsaved')
      clearTimeout(timer)
      timer = setTimeout(() => void flush(), delayMs)
    },
    flush,
    /** The user chose their own text: save it now (the caller has already moved the save's base to the newest version). */
    keepMine() {
      if (state !== 'conflict' || pending === null) return Promise.resolve()
      setState('unsaved')
      return flush()
    },
    /** Reopening text kept from a conflict: it stays unsaved until the user picks a side. */
    markConflict(text: string) {
      pending = text
      setState('conflict')
    },
    /** The user chose the server's version: drop the unsaved text and save again from here. */
    reload() {
      clearTimeout(timer)
      pending = null
      setState('saved')
    },
    activate: () => { disposed = false },
    dispose: () => {
      disposed = true
      clearTimeout(timer)
    },
  }
}
