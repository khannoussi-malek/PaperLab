import { Loader2, TriangleAlert } from 'lucide-react'
import { lazy, Suspense, useRef, useState } from 'react'
import { api, type Diagram } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { RemoteConfirm } from '../review/RemoteConfirm'
import { remoteHost } from '../review/reviewModel'
import { canInsert, diagramBlock, diagramLabel, diagramPackages, diagramProblem, diagramStartError, editableCode, isLive } from './diagramModel'
import { useDiagram } from './useDiagram'
import type { InsertResult } from './useInsertBlock'

const AI = <span className="rounded bg-provenance-llm-surface px-1.5 py-px text-xs text-provenance-llm">AI</span>
// pdf.js loads with the first preview, not with the editor toolbar.
const DiagramPreview = lazy(() => import('./DiagramPreview'))

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  manuscriptId: string
  labelTexts: () => string[]
  onInsert: (code: string, packages: string[]) => Promise<InsertResult>
  onClosed?: (inserted: boolean) => void
}

/**
 * Insert → Diagram…: TikZ drawn by the model from the researcher's own description, previewed and editable, and put
 * into the file only by the Insert click (D118). Esc, Cancel and closing drop the draft.
 */
export function DiagramDialog({ open, onOpenChange, manuscriptId, labelTexts, onInsert, onClosed }: Props) {
  const d = useDiagram(manuscriptId)
  const row = d.diagram
  const inserted = useRef(false)
  const inserting = useRef(false)
  const [description, setDescription] = useState('')
  const [host, setHost] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)
  const [tab, setTab] = useState('preview')

  const close = () => {
    void d.discard()
    onOpenChange(false)
  }
  const run = async (step: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await step()
    } catch (e) {
      const remote = remoteHost(e)
      if (remote) setHost(remote)
      else setError(diagramStartError(e))
    } finally {
      setBusy(false)
    }
  }
  const start = (confirmRemote: boolean) => run(async () => {
    setHost(null)
    await d.create(row?.description ?? description, confirmRemote)
    setDraft(null)
  })
  const regenerate = () => run(async () => { await d.regenerate(); setDraft(null) })

  const insert = async () => {
    if (inserting.current || !row || !canInsert(row)) return
    inserting.current = true
    setBusy(true)
    setError(null)
    try {
      // The label is numbered against the live text of every file at click time.
      const result = await onInsert(diagramBlock(row.code!, diagramLabel(labelTexts(), row.description)), diagramPackages(row.libraries))
      if (result.ok) {
        inserted.current = true
        close()
      } else setError(result.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      inserting.current = false
      setBusy(false)
    }
  }

  const live = row !== null && isLive(row)
  const shownCode = row ? (draft ?? editableCode(row)) : ''
  const dirty = row !== null && draft !== null && draft !== editableCode(row)
  const problem = row && !live ? diagramProblem(row) : null

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" onCloseAutoFocus={(e) => { e.preventDefault(); onClosed?.(inserted.current) }}>
        <DialogHeader>
          <DialogTitle>Draw a diagram</DialogTitle>
          <DialogDescription>PaperLab's model draws a TikZ figure from your words. Nothing goes into your file until you click Insert.</DialogDescription>
        </DialogHeader>
        {host ? (
          <RemoteConfirm what="text" host={host} onSend={() => void start(true)} onCancel={() => setHost(null)} />
        ) : (
          <>
            {row === null ? (
              <div className="space-y-1.5">
                <label htmlFor="diagram-description" className="text-sm font-medium">Describe your diagram in a few words</label>
                <Textarea id="diagram-description" rows={3} maxLength={2000} value={description} aria-describedby="diagram-hint" onChange={(e) => setDescription(e.target.value)} />
                <div id="diagram-hint" className="space-y-0.5 text-xs text-muted-foreground">
                  <p>For example: A pipeline: "Raw data" → "Cleaning" → "Model" → "Report"</p>
                  <p>Use the words you want on the boxes — they're used as the labels.</p>
                </div>
              </div>
            ) : (
              <Draft row={row} manuscriptId={manuscriptId} live={live} busy={busy} tab={tab} onTab={setTab} code={shownCode} dirty={dirty}
                onCode={setDraft} onUpdate={() => void run(async () => { await d.editCode(shownCode); setDraft(null) })}
                onCancelRun={() => void run(d.cancel)} />
            )}
            <div aria-live="polite" className="space-y-1 text-sm">
              {error && <p className="text-destructive">{error}</p>}
              {problem && <p className="flex items-center gap-1.5 text-destructive"><TriangleAlert className="size-4 shrink-0" aria-hidden />{problem}</p>}
              {row && !live && row.errors.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5 text-destructive">
                  {row.errors.map((e, i) => <li key={i}>{e.line ? `Line ${e.line}: ${e.message}` : e.message}</li>)}
                </ul>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>Cancel</Button>
              {row === null ? (
                <Button type="button" disabled={busy || !description.trim()} onClick={() => void start(false)}>{busy ? 'Starting…' : 'Generate'}</Button>
              ) : (
                <>
                  <Button type="button" variant="outline" disabled={busy || live} onClick={() => void regenerate()}>Regenerate</Button>
                  <Button type="button" disabled={busy || live || dirty || !canInsert(row)} onClick={() => void insert()}>Insert</Button>
                </>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Draft({ row, manuscriptId, live, busy, tab, onTab, code, dirty, onCode, onUpdate, onCancelRun }: {
  row: Diagram
  manuscriptId: string
  live: boolean
  busy: boolean
  tab: string
  onTab: (tab: string) => void
  code: string
  dirty: boolean
  onCode: (code: string) => void
  onUpdate: () => void
  onCancelRun: () => void
}) {
  const drawn = row.status === 'done' && row.compiled === true
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm">{AI}<span className="text-muted-foreground">From your description: {row.description}</span></p>
      <div className="flex items-center gap-2 text-sm">
        <p role="status" className="flex items-center gap-1.5">
          {live && <><Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />{row.code === null ? 'Drawing your diagram…' : 'Updating the preview…'}</>}
        </p>
        {live && <Button type="button" size="sm" variant="outline" aria-label="Cancel drawing" disabled={busy} onClick={onCancelRun}>Cancel</Button>}
      </div>
      {row.labels_not_in_description.length > 0 && (
        <p className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-500"><TriangleAlert className="size-4 shrink-0" aria-hidden />These labels weren't in your description: {row.labels_not_in_description.join(', ')}</p>
      )}
      {/* A failed or interrupted generation has no code: Regenerate, not an editor (Task 7 review). */}
      {row.code !== null && (
        <Tabs value={tab} onValueChange={onTab}>
          <TabsList>
            <TabsTrigger value="preview">Preview</TabsTrigger>
            <TabsTrigger value="latex">LaTeX</TabsTrigger>
          </TabsList>
          <TabsContent value="preview" forceMount className="data-[state=inactive]:hidden">
            {drawn
              ? <Suspense fallback={<p className="text-sm text-muted-foreground">Loading the preview…</p>}><DiagramPreview url={api.manuscriptDiagramPdfUrl(manuscriptId, row.id, row.updated_at)} /></Suspense>
              : <p className="text-sm text-muted-foreground">{live ? 'The preview shows once it is drawn.' : 'No preview: the diagram didn\'t compile.'}</p>}
          </TabsContent>
          <TabsContent value="latex" className="space-y-2">
            <Textarea aria-label="LaTeX" rows={12} spellCheck={false} className="font-mono text-xs" value={code} onChange={(e) => onCode(e.target.value)} />
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onUpdate}>Update preview</Button>
              {dirty && <span className="text-xs text-muted-foreground">Update the preview to insert your changes.</span>}
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
