export type SaveState = 'saved' | 'saving' | 'unsaved' | 'conflict'

type Options = {
  delayMs: number
  /** Resolves `{ conflict: true }` when the file changed elsewhere; a rejection leaves the text unsaved. */
  save: (text: string) => Promise<{ conflict: boolean } | void>
  onState?: (state: SaveState) => void
  onError?: (error: Error) => void
}

/** Saves the latest text `delayMs` after the last change. One save at a time; a conflict stops it until `reload()`. */
export function createAutosave({ delayMs, save, onState, onError }: Options) {
  let state: SaveState = 'saved'
  let pending: string | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let queue: Promise<void> = Promise.resolve()

  const setState = (next: SaveState) => {
    state = next
    onState?.(next)
  }

  async function run() {
    if (state === 'conflict' || pending === null) return
    const text = pending
    pending = null
    setState('saving')
    try {
      const result = await save(text)
      if (result?.conflict) {
        pending = null
        setState('conflict')
      } else setState(pending === null ? 'saved' : 'unsaved')
    } catch (error) {
      pending ??= text
      setState('unsaved')
      onError?.(error instanceof Error ? error : new Error(String(error)))
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
    change(text: string) {
      if (state === 'conflict') return
      pending = text
      setState('unsaved')
      clearTimeout(timer)
      timer = setTimeout(() => void flush(), delayMs)
    },
    flush,
    /** After the user reloads the file: forget the unsaved text and save again from here. */
    reload() {
      clearTimeout(timer)
      pending = null
      setState('saved')
    },
    dispose: () => clearTimeout(timer),
  }
}
