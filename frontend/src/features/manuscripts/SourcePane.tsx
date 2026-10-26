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

type Props = {
  manuscriptId: string
  path: string
  errors: { line: number; message: string }[]
  jumpTo: { line: number; n: number } | null
  compiling: boolean
  compileError: string | null
  onCompile: () => void
  onText: (path: string, text: string) => void
}

/**
 * One file in the editor, with its own autosave. The page keys this by file, so leaving a file unmounts it, and the
 * unmount flushes whatever is still waiting to be saved.
 */
export function SourcePane({ manuscriptId, path, errors, jumpTo, compiling, compileError, onCompile, onText }: Props) {
  const file = useManuscriptFile(manuscriptId, path)
  const save = useSaveManuscriptFile()
  const saveRef = useRef(save.mutateAsync)
  saveRef.current = save.mutateAsync
  const base = useRef<string | null>(null) // the file's updated_at as we last saw it
  const [text, setText] = useState<string | null>(null)
  const [state, setState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<Error | null>(null)
  const [auto] = useState(() =>
    createAutosave({
      delayMs: AUTOSAVE_MS,
      onState: (s) => { setState(s); if (s === 'saved') setSaveError(null) },
      onError: setSaveError,
      save: async (body) => {
        const result = await saveRef.current({ id: manuscriptId, path, text: body, base: base.current })
        if (!result.conflict) base.current = result.updatedAt
        return result
      },
    }),
  )

  // Take the server's text the first time, and again when it changed under us (a restore) while nothing here is unsaved.
  useEffect(() => {
    const data = file.data
    if (!data) return
    if (base.current === null || (data.updated_at !== base.current && auto.state === 'saved')) {
      base.current = data.updated_at
      setText(data.text)
    }
  }, [file.data, auto])

  useEffect(() => () => { void auto.flush() }, [auto])

  const compileNow = async () => {
    await auto.flush()
    if (auto.state === 'saved') onCompile()
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

  const reload = async () => {
    const fresh = await file.refetch()
    if (!fresh.data) return
    base.current = fresh.data.updated_at
    setText(fresh.data.text)
    onText(path, fresh.data.text)
    auto.reload()
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
            <span>{manuscriptErrorMessage('file_changed')} Reload to see that version; the edits in this tab are dropped.</span>
            <Button size="sm" variant="outline" onClick={() => void reload()}>Reload</Button>
          </AlertDescription>
        </Alert>
      )}
      {saveError && state !== 'conflict' && (
        <Alert variant="destructive" className="m-2 w-auto"><AlertDescription>{manuscriptFailure(saveError)}</AlertDescription></Alert>
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
