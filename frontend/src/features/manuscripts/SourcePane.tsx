import { Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { useManuscriptFile, useSaveManuscriptFile } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { createAutosave, type SaveState } from './autosave'
import { manuscriptErrorMessage, manuscriptFailure } from './errors'
import { keptTexts, useKeptTexts, type KeptText } from './keptTexts'
import { KeptTextAlert } from './KeptTextAlert'
import { LatexEditor } from './LatexEditor'

const AUTOSAVE_MS = 1000
const SAVE_LABEL: Record<SaveState, string> = {
  saved: 'Saved',
  saving: 'Saving…',
  unsaved: 'Unsaved changes',
  conflict: 'Changed in another tab',
}

type Props = {
  manuscriptId: string
  path: string
  errors: { line: number; message: string }[]
  jumpTo: { line: number; n: number } | null
  compiling: boolean
  compileError: string | null
  onCompile: () => void
  /** The text as it now is (for the outline), or null once it is the server's again. */
  onText: (path: string, text: string | null) => void
  onState: (path: string, state: SaveState) => void
  /** Hands the page a way to save what is pending; it resolves true when nothing is left unsaved. */
  registerFlush: (flush: (() => Promise<boolean>) | null) => void
}

/**
 * One file in the editor, with its own autosave. The page keys this by file, so leaving a file unmounts it, and the
 * unmount flushes whatever is waiting; if that save fails, the text is handed to the page (`onKeep`), not dropped.
 */
export function SourcePane(props: Props) {
  const { manuscriptId, path, errors, jumpTo, compiling, compileError, onCompile, onText } = props
  const file = useManuscriptFile(manuscriptId, path)
  const save = useSaveManuscriptFile()
  const live = useRef({ ...props, mutate: save.mutateAsync })
  live.current = { ...props, mutate: save.mutateAsync }
  const base = useRef<string | null>(null) // the file's updated_at as we last saw it
  const newest = useRef<string | null>(null) // the server's updated_at a conflict reported
  const [text, setText] = useState<string | null>(null)
  const [state, setState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<Error | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [seq] = useState(() => keptTexts.nextSeq()) // this pane's own entry id in the kept-text store
  const owned = useRef<readonly string[]>([]) // entries this pane took over: its text holds theirs
  const entries = useKeptTexts(manuscriptId).filter((k) => k.path === path && !owned.current.includes(k.id))
  const [auto] = useState(() =>
    createAutosave({
      delayMs: AUTOSAVE_MS,
      onState: (s) => {
        setState(s)
        if (s === 'saved') setSaveError(null)
      },
      onError: (error, willRetry) => { setSaveError(error); setRetrying(willRetry) },
      retryable: (error) => !(error instanceof ApiError) || error.status >= 500, // a 4xx fails the same way again
      save: async (body) => {
        const result = await live.current.mutate({ id: manuscriptId, path, text: body, base: base.current })
        if (result.conflict) newest.current = result.updatedAt
        else {
          base.current = result.updatedAt
          // The server took text built on the entries this pane took over, so they are settled. Entries it did not
          // take over (another pane's copy) are never this pane's to remove.
          owned.current.forEach(keptTexts.remove)
          owned.current = []
        }
        return result
      },
    }),
  )

  // Takes over a kept text: it goes into the editor, and stays unsaved until saved. Text edited against an older version
  // never goes over a newer one unasked: that is a conflict to resolve.
  const adopt = (kept: KeptText, serverAt: string) => {
    owned.current = [...owned.current, kept.id]
    setText(kept.text)
    onText(path, kept.text)
    if (kept.reason === 'conflict' || (kept.base !== null && kept.base !== serverAt)) {
      newest.current = serverAt
      auto.markConflict(kept.text)
    } else auto.change(kept.text)
  }

  // Take the server's text the first time (or the kept text), and again when it changed under us (a restore) while
  // nothing here is unsaved.
  useEffect(() => {
    const data = file.data
    if (!data) return
    if (base.current === null) {
      base.current = data.updated_at
      // One kept copy is taken over at once; several wait for the user to pick (each has its own alert).
      const kept = keptTexts.forManuscript(manuscriptId).filter((k) => k.path === path)
      if (kept.length !== 1) return setText(data.text)
      adopt(kept[0], data.updated_at)
    } else if (data.updated_at !== base.current && auto.state === 'saved') {
      base.current = data.updated_at
      setText(data.text)
      onText(path, null)
    }
  }, [file.data, auto, onText, path, manuscriptId])

  useEffect(() => { live.current.onState(path, state) }, [state, path])

  const flushNow = async () => {
    await auto.flush()
    return auto.state === 'saved'
  }
  useEffect(() => {
    auto.activate()
    live.current.registerFlush(flushNow)
    return () => {
      const { onState, registerFlush } = live.current
      registerFlush(null)
      const unsaved = auto.state !== 'saved' || auto.unsavedText !== null
      if (unsaved) keptTexts.flushStarted() // the leave warning stays on until this settles
      void auto.flush().then(() => {
        if (auto.state !== 'saved' && auto.unsavedText !== null) {
          const kept = { path, text: auto.unsavedText, reason: auto.state === 'conflict' ? 'conflict' : 'error', base: base.current, seq } as const
          keptTexts.put(manuscriptId, kept, owned.current) // replaces only what this pane took over
        }
        if (unsaved) keptTexts.flushSettled()
        onState(path, 'saved')
      })
      auto.dispose()
    }
  }, [auto, path])

  const compileNow = async () => {
    if (text === null) return
    const ok = await flushNow()
    if (ok && !live.current.compiling) onCompile()
  }
  const compileRef = useRef(compileNow)
  compileRef.current = compileNow

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's') return
      event.preventDefault() // not the browser's save dialog
      void compileRef.current()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const loadTheirs = async () => {
    const fresh = await file.refetch()
    if (fresh.isError || !fresh.data) return // keep my text and the conflict; the error shows above
    base.current = fresh.data.updated_at
    setText(fresh.data.text)
    onText(path, null)
    owned.current = [] // the user chose theirs: the copies this pane took over show again, to use or discard
    auto.reload()
  }

  const keepMine = () => {
    base.current = newest.current ?? base.current
    void auto.keepMine()
  }

  const change = (next: string) => {
    setText(next)
    onText(path, next)
    auto.change(next)
  }

  return (
    <section aria-label={`Editing ${path}`} className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-glass-border px-3 py-1.5">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{path}</span>
        <span aria-live="polite" className="text-xs text-muted-foreground">{SAVE_LABEL[state]}</span>
        <Button size="sm" disabled={compiling || text === null} onClick={() => void compileNow()}>
          {compiling && <Loader2 aria-hidden className="animate-spin motion-reduce:animate-none" />}
          {compiling ? 'Compiling…' : 'Compile'}
        </Button>
      </div>
      {state === 'conflict' && (
        <Alert variant="destructive" className="m-2 w-auto">
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{manuscriptErrorMessage('file_changed')} Your text is kept until you choose.</span>
            <Button size="sm" variant="outline" onClick={keepMine}>Keep my version</Button>
            <Button size="sm" variant="outline" onClick={() => void loadTheirs()}>Load theirs</Button>
          </AlertDescription>
        </Alert>
      )}
      {file.data && entries.map((entry) => (
        <KeptTextAlert
          key={entry.id}
          path={path}
          kept={entry}
          action={<Button size="sm" variant="outline" disabled={state !== 'saved'} onClick={() => adopt(entry, base.current ?? file.data!.updated_at)}>Use it</Button>}
          onDiscard={() => keptTexts.remove(entry.id)}
        />
      ))}
      {saveError && state !== 'conflict' && (
        <Alert variant="destructive" className="m-2 w-auto"><AlertDescription>{manuscriptFailure(saveError)}{retrying && ' Trying again shortly.'}</AlertDescription></Alert>
      )}
      {compileError && <Alert variant="destructive" className="m-2 w-auto"><AlertDescription>{compileError}</AlertDescription></Alert>}
      {file.error && <Alert variant="destructive" className="m-2 w-auto"><AlertDescription>{file.error.message}</AlertDescription></Alert>}
      <div className="min-h-0 flex-1">
        {text === null ? (!file.error && <TabSkeleton label="Loading file" />) : (
          <LatexEditor value={text} onChange={change} errors={errors} jumpTo={jumpTo} onSave={() => void compileNow()} />
        )}
      </div>
    </section>
  )
}
