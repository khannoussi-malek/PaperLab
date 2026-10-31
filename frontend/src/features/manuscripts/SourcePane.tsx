import { Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Role, type SectionReview, type SectionSpan } from '@/api/client'
import { useManuscriptFile, useSaveManuscriptFile } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { createAutosave, type SaveState } from './autosave'
import { manuscriptErrorMessage, manuscriptFailure } from './errors'
import { keptTexts, useKeptTexts, type KeptText } from './keptTexts'
import { KeptTextAlert } from './KeptTextAlert'
import type { DeckPaper } from './deck/deckModel'
import { LatexEditor } from './LatexEditor'
import { replaceSpan } from './pdfEdit'
import type { PreambleEdit } from './results/insertBlock'
import { InsertMenu } from './results/InsertMenu'
import { ReviewMenu } from './review/ReviewMenu'
import { ReviewPanel } from './review/ReviewPanel'
import type { ReviewHandle } from './review/reviewMarks'
import { useReview } from './review/useReview'
import { useReviewInEditor } from './review/useReviewInEditor'
import { RemoteConfirmDialog } from './review/RemoteConfirm'
import { SectionReviewDialog } from './review/SectionReviewDialog'
import { sectionAt } from './review/sectionReviewModel'
import { useSectionReview } from './review/useSectionReview'

const AUTOSAVE_MS = 1000
const POLL_MS = 5000
const NOTICE_MS = 8000
// Snapshots this tab's own actions take (a restore, a section move/rename): no notice for those.
const OWN_REASONS = ['before_restore', 'before_sections']
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
  onCursor?: (line: number) => void
  onSectionStep?: (step: -1 | 1) => void
  onShowInPdf?: (line: number) => void
  /** The text as it now is (for the outline), or null once it is the server's again. */
  onText: (path: string, text: string | null) => void
  onState: (path: string, state: SaveState) => void
  /** Hands the page a way to save what is pending; it resolves true when nothing is left unsaved. */
  registerFlush: (flush: (() => Promise<boolean>) | null) => void
  onCiteKey?: (key: string) => void
  /** Mod-E: the open file's text and the selection (or cursor) to find evidence for. */
  onFindEvidence?: (doc: string, from: number, to: number) => void
  /** The manuscript's workspace; the reviewer checks citations against its papers. */
  workspaceId?: string | null
  citeOptions?: DeckPaper[]
  onCite?: (paperId: string) => void
  /** Puts a table or figure at the cursor with the packages it needs (the Insert menu, next). */
  onInsertBlock?: (code: string, packages: string[]) => Promise<{ ok: true } | { ok: false; message: string }>
  /** Every file's live text, for unique labels. */
  labelTexts?: () => string[]
  /** The manuscript's file paths, for a unique name for an uploaded picture. */
  filePaths?: () => string[]
  /** Hands the page a way to insert text at the editor's cursor, as a normal edit (optionally with a preamble edit in the same change). */
  registerInsert?: (insert: ((text: string, block?: boolean, preamble?: PreambleEdit) => void) | null) => void
  registerFindEvidence?: (run: (() => boolean) | null) => void
  /** Hands the page a way to replace part of a line in the editor's buffer, as a normal edit (autosave picks it up). */
  registerReplace?: (replace: ((line: number, start: number, end: number, text: string) => void) | null) => void
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

  // A quiet line saying who changed the file: the newest snapshot's reason tells Claude's write from any other.
  const [notice, setNotice] = useState<string | null>(null)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const announceOutside = async () => {
    const reason = await api.listManuscriptSnapshots(manuscriptId).then((s) => s[0]?.reason, () => undefined)
    if (!mounted.current || (reason !== undefined && OWN_REASONS.includes(reason))) return // this tab's own change
    setNotice(reason === 'before_mcp' ? 'Updated by Claude (MCP)' : reason === undefined ? 'Updated' : 'Updated elsewhere')
  }
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [notice])

  // While nothing here is unsaved, look for outside changes on focus and every few seconds (never while hidden). The
  // effect below applies a newer version only if the buffer is still clean when the answer arrives.
  const ready = text !== null && state === 'saved'
  const { refetch } = file
  useEffect(() => {
    if (!ready) return
    const poll = () => { if (document.visibilityState === 'visible') void refetch({ cancelRefetch: false }) } // a slow answer is not cancelled by the next tick
    const timer = setInterval(poll, POLL_MS)
    window.addEventListener('focus', poll)
    return () => { clearInterval(timer); window.removeEventListener('focus', poll) }
  }, [ready, refetch])

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
    } else if (Date.parse(data.updated_at) > Date.parse(base.current) && auto.state === 'saved') { // newer only: a stale answer never rolls back our own save
      base.current = data.updated_at
      setText(data.text)
      onText(path, null)
      void announceOutside()
    }
  }, [file.data, auto, state, onText, path, manuscriptId]) // `state`: a write that landed while saving is taken once saved

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

  const textNow = useRef<string | null>(null)
  textNow.current = text
  const change = (next: string) => {
    textNow.current = next
    setText(next)
    onText(path, next)
    auto.change(next)
  }

  useEffect(() => {
    live.current.registerReplace?.((line, start, end, replacement) => {
      if (textNow.current !== null) changeRef.current(replaceSpan(textNow.current, { line, start, end }, replacement))
    })
    return () => live.current.registerReplace?.(null)
  }, [path])
  const changeRef = useRef(change)
  changeRef.current = change

  const isTex = /\.tex$/i.test(path)
  const review = useReview(manuscriptId, path, isTex)
  const [reviewHandleRef, setReviewHandle] = useState<ReviewHandle | null>(null)
  const sectionReview = useSectionReview(manuscriptId, path, isTex)
  const inEditor = useReviewInEditor({ manuscriptId, workspaceId: props.workspaceId ?? null, review, text, handle: reviewHandleRef, flush: flushNow, getBase: () => base.current, sections: { file: path, reviews: sectionReview.reviews } })
  const [sectionTarget, setSectionTarget] = useState<{ at: number; section: SectionSpan | null; role?: Role; gone?: boolean } | null>(null)
  // The section under the cursor, or for Review again the section of that title as the text now reads.
  const openSectionReview = async (again?: SectionReview) => {
    const now = textNow.current
    if (now === null) return
    // ponytail: a failed locate reads as "no section here"; say more if it ever happens in practice
    const spans = await api.locateSections(manuscriptId, path, now).then((r) => r.sections, () => [] as SectionSpan[])
    const cursor = reviewHandleRef?.cursor() ?? 0
    const section = again ? spans.find((s) => s.title === again.title) ?? null : sectionAt(spans, cursor)
    setSectionTarget({ at: again ? section?.start ?? 0 : cursor, section, role: again?.role_source === 'chosen' ? again.role : undefined, gone: !!again && !section })
  }
  const startSectionReview = async (role: Role | null, confirmRemote: boolean) => {
    if (!(await flushNow())) throw new Error("Your latest changes aren't saved yet. Try again in a moment.")
    if (!base.current || !sectionTarget) throw new Error('The file is still loading. Try again.')
    await sectionReview.start({ base: base.current, at: sectionTarget.at, role, confirmRemote })
  }

  return (
    <section aria-label={`Editing ${path}`} className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-glass-border px-3 py-1.5">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{path}</span>
        <span aria-live="polite" className="text-xs text-muted-foreground">{SAVE_LABEL[state]}</span>
        {props.onInsertBlock && /\.tex$/i.test(path) && <InsertMenu manuscriptId={manuscriptId} labelTexts={props.labelTexts ?? (() => [])} filePaths={props.filePaths ?? (() => [])} onInsert={props.onInsertBlock} />}
        {isTex && <ReviewMenu hasWorkspace={!!props.workspaceId} run={review.anyRun} onCheck={() => void inEditor.check()} onCancel={() => void review.cancel()} onReviewSection={() => void openSectionReview()} sectionLive={sectionReview.live} />}
        <Button size="sm" disabled={compiling || text === null} onClick={() => void compileNow()}>
          {compiling && <Loader2 aria-hidden className="animate-spin motion-reduce:animate-none" />}
          {compiling ? 'Compiling…' : 'Compile'}
        </Button>
      </div>
      <div aria-live="polite">
        {notice && (
          <p className="flex items-center gap-2 border-b border-glass-border px-3 py-1 text-xs text-muted-foreground">
            <span>{notice}</span>
            <Button size="sm" variant="ghost" className="h-5 px-1 text-xs" onClick={() => setNotice(null)}>Dismiss</Button>
          </p>
        )}
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
          <LatexEditor value={text} onChange={change} errors={errors} jumpTo={jumpTo} onCursor={props.onCursor} onSectionStep={props.onSectionStep} onShowInPdf={props.onShowInPdf} onCiteKey={props.onCiteKey} onFindEvidence={props.onFindEvidence} citeOptions={props.citeOptions} onCite={props.onCite} registerInsert={props.registerInsert} registerFindEvidence={props.registerFindEvidence} registerReview={setReviewHandle} reviewLocate={(t) => api.locateSentences(manuscriptId, t).then((r) => r.sentences)} onSave={() => void compileNow()} />
        )}
      </div>
      {isTex && (
        <>
          <ReviewPanel manuscriptId={manuscriptId} review={review} stale={inEditor.stale} onJump={inEditor.jump} onCite={inEditor.cite} onCheckAgain={() => void inEditor.check()}
            sections={{ reviews: sectionReview.reviews, stale: inEditor.sectionStale, hasWorkspace: !!props.workspaceId, live: sectionReview.live, onCancel: (id) => void sectionReview.cancel(id), onReviewAgain: (r) => void openSectionReview(r) }} />
          <RemoteConfirmDialog what="text" host={review.confirmHost} onSend={() => void inEditor.check(true)} onCancel={review.dismissConfirm} />
          <SectionReviewDialog target={sectionTarget} onClose={() => setSectionTarget(null)} onStart={startSectionReview} />
        </>
      )}
    </section>
  )
}
