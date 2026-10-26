import { Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useManuscriptFile, useSaveManuscriptFile } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { createAutosave, type SaveState } from './autosave'
import { manuscriptErrorMessage, manuscriptFailure } from './errors'
import { LatexEditor } from './LatexEditor'

const AUTOSAVE_MS = 1000
const SAVE_LABEL: Record<SaveState, string> = {
  saved: 'Saved',
  saving: 'Saving…',
  unsaved: 'Unsaved changes',
  conflict: 'Changed in another tab',
}

/** Text a file's pane could not save when it closed, handed back when the file is opened again. */
export type KeptText = { text: string; reason: 'conflict' | 'error' }

type Props = {
  manuscriptId: string
  path: string
  errors: { line: number; message: string }[]
  jumpTo: { line: number; n: number } | null
  compiling: boolean
  compileError: string | null
  kept: KeptText | null
  onCompile: () => void
  /** The text as it now is (for the outline), or null once it is the server's again. */
  onText: (path: string, text: string | null) => void
  onKeep: (path: string, kept: KeptText) => void
  onAdopted: (path: string) => void
  onState: (path: string, state: SaveState) => void
  /** Hands the page a way to save what is pending; it resolves true when nothing is left unsaved. */
  registerFlush: (flush: (() => Promise<boolean>) | null) => void
}

/**
 * One file in the editor, with its own autosave. The page keys this by file, so leaving a file unmounts it, and the
 * unmount flushes whatever is waiting; if that save fails, the text is handed to the page (`onKeep`), not dropped.
 */
export function SourcePane(props: Props) {
  const { manuscriptId, path, errors, jumpTo, compiling, compileError, kept, onCompile, onText } = props
  const file = useManuscriptFile(manuscriptId, path)
  const save = useSaveManuscriptFile()
  const live = useRef({ ...props, mutate: save.mutateAsync })
  live.current = { ...props, mutate: save.mutateAsync }
  const base = useRef<string | null>(null) // the file's updated_at as we last saw it
  const newest = useRef<string | null>(null) // the server's updated_at a conflict reported
  const [text, setText] = useState<string | null>(null)
  const [state, setState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<Error | null>(null)
  const [auto] = useState(() =>
    createAutosave({
      delayMs: AUTOSAVE_MS,
      onState: (s) => { setState(s); if (s === 'saved') setSaveError(null) },
      onError: setSaveError,
      save: async (body) => {
        const result = await live.current.mutate({ id: manuscriptId, path, text: body, base: base.current })
        if (result.conflict) newest.current = result.updatedAt
        else base.current = result.updatedAt
        return result
      },
    }),
  )

  // Take the server's text the first time (or the kept text), and again when it changed under us (a restore) while
  // nothing here is unsaved.
  useEffect(() => {
    const data = file.data
    if (!data) return
    if (base.current === null) {
      base.current = data.updated_at
      if (!kept) return setText(data.text)
      setText(kept.text)
      onText(path, kept.text)
      if (kept.reason === 'conflict') {
        newest.current = data.updated_at
        auto.markConflict(kept.text)
      } else auto.change(kept.text)
      live.current.onAdopted(path)
    } else if (data.updated_at !== base.current && auto.state === 'saved') {
      base.current = data.updated_at
      setText(data.text)
      onText(path, null)
    }
  }, [file.data, auto, kept, onText, path])

  useEffect(() => { live.current.onState(path, state) }, [state, path])

  const flushNow = async () => {
    await auto.flush()
    return auto.state === 'saved'
  }
  useEffect(() => {
    auto.activate()
    live.current.registerFlush(flushNow)
    return () => {
      const { onKeep, onState, registerFlush } = live.current
      registerFlush(null)
      void auto.flush().then(() => {
        if (auto.state !== 'saved' && auto.unsavedText !== null) {
          onKeep(path, { text: auto.unsavedText, reason: auto.state === 'conflict' ? 'conflict' : 'error' })
        }
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
    if (!fresh.data) return
    base.current = fresh.data.updated_at
    setText(fresh.data.text)
    onText(path, null)
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
      {saveError && state !== 'conflict' && (
        <Alert variant="destructive" className="m-2 w-auto"><AlertDescription>{manuscriptFailure(saveError)} Trying again shortly.</AlertDescription></Alert>
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
