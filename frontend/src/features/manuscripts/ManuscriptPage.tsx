import { useQueries } from '@tanstack/react-query'
import { Download, History } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/api/client'
import { useCompileManuscript, useManuscript } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { loadPanelWidth, panelTrack, savePanelWidth } from '@/components/panelWidth'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { Button } from '@/components/ui/button'
import { LoadError } from '@/features/library/ErrorAlert'
import { browserStorage } from '@/features/notes/highlightColors'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { manuscriptHref, workspaceHref } from '@/lib/route'
import { errorsFor } from './compileErrors'
import { manuscriptFailure } from './errors'
import { FileList } from './FileList'
import { FinalStepsChecklist } from './FinalStepsChecklist'
import { HistoryDialog } from './HistoryDialog'
import { outline } from './outline'
import { OutlinePanel } from './OutlinePanel'
import { PdfPane } from './PdfPane'
import { MANUSCRIPT_PDF } from './pdfPanel'
import type { SaveState } from './autosave'
import { keptTexts, useKeptTexts } from './keptTexts'
import { KeptTextAlert } from './KeptTextAlert'
import { SourcePane } from './SourcePane'
import { useLeaveWarning } from './useLeaveWarning'

/** The writing studio: files and outline | source | PDF. `file` is the `?file=` of the route; null is the main file. */
export function ManuscriptPage({ manuscriptId, file }: { manuscriptId: string; file: string | null }) {
  const manuscript = useManuscript(manuscriptId)
  const compile = useCompileManuscript()
  const data = manuscript.data
  const [live, setLive] = useState<Record<string, string>>({})
  const [jump, setJump] = useState<{ line: number; n: number } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const kept = useKeptTexts(manuscriptId) // text a closed file could not save; lives outside the page
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({})
  const flushRef = useRef<(() => Promise<boolean>) | null>(null)
  useLeaveWarning(Object.values(saveStates).some((s) => s !== 'saved')) // kept texts are warned about in App
  const onText = useCallback(
    (p: string, text: string | null) =>
      setLive((l) => (text === null ? Object.fromEntries(Object.entries(l).filter(([k]) => k !== p)) : { ...l, [p]: text })),
    [],
  )
  const onState = useCallback((p: string, s: SaveState) => setSaveStates((all) => ({ ...all, [p]: s })), [])
  const registerFlush = useCallback((f: (() => Promise<boolean>) | null) => { flushRef.current = f }, [])
  const [pdfWidth, setPdfWidth] = useState(() => loadPanelWidth(MANUSCRIPT_PDF, browserStorage()))
  useEffect(() => savePanelWidth(MANUSCRIPT_PDF, browserStorage(), pdfWidth), [pdfWidth])

  const path = data && (file && data.files.some((f) => f.path === file) ? file : data.main_file)
  // Same keys as the editor's own query, so the open file is fetched once; the others feed the outline.
  const texFiles = (data?.files ?? []).filter((f) => f.path.endsWith('.tex'))
  const texQueries = useQueries({
    queries: texFiles.map((f) => ({ queryKey: ['manuscripts', manuscriptId, 'file', f.path], queryFn: () => api.getManuscriptFile(manuscriptId, f.path) })),
  })
  const texts = texQueries.map((q) => q.data?.text).join('\u0000')
  const items = useMemo(() => {
    const files = Object.fromEntries(texFiles.flatMap((f, i) => (texQueries[i].data ? [[f.path, texQueries[i].data.text]] : [])))
    return data ? outline({ ...files, ...live }, data.main_file) : []
  }, [data?.main_file, texts, live])
  const errors = useMemo(() => (path && data ? errorsFor(data.compile_errors, path) : []), [data?.compile_errors, path])

  useEffect(() => setJump(null), [path]) // a jump belongs to the file it was made in

  const compiling = compile.isPending || data?.compile_status === 'running' || data?.compile_requested === true
  const clamped = Math.min(Math.max(pdfWidth, MANUSCRIPT_PDF.minWidth), Math.floor(window.innerWidth * MANUSCRIPT_PDF.maxShare))

  return (
    <AppShell
      fills
      title={data?.title ?? 'Manuscript'}
      back={data?.workspace_id ? { href: workspaceHref(data.workspace_id, 'write'), label: 'Back to workspace' } : undefined}
      actions={data && (
        <>
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}><History aria-hidden />History</Button>
          <Button variant="ghost" size="sm" asChild>
            <a href={api.manuscriptExportUrl(manuscriptId)} download><Download aria-hidden />Download zip</a>
          </Button>
        </>
      )}
    >
      {manuscript.error && <LoadError message={manuscript.error.message} onRetry={() => void manuscript.refetch()} />}
      {manuscript.isPending && <TabSkeleton label="Loading manuscript" />}
      {Object.entries(kept).filter(([keptPath]) => keptPath !== path).map(([keptPath, k]) => (
        <KeptTextAlert
          key={keptPath}
          path={keptPath}
          kept={k}
          action={<Button size="sm" variant="outline" asChild><a href={manuscriptHref(manuscriptId, keptPath)}>Open it</a></Button>}
          onDiscard={() => keptTexts.remove(manuscriptId, keptPath)}
        />
      ))}
      {data && path && (
        <div className="grid min-h-0 flex-1 overflow-hidden" style={{ gridTemplateColumns: `14rem minmax(0,1fr) ${panelTrack(MANUSCRIPT_PDF, pdfWidth)}` }}>
          <div className="flex min-h-0 flex-col gap-4 overflow-auto border-r border-glass-border py-2">
            <FileList manuscriptId={manuscriptId} files={data.files} current={path} main={data.main_file} />
            <OutlinePanel manuscriptId={manuscriptId} items={items} currentFile={path} onJump={(line) => setJump((j) => ({ line, n: (j?.n ?? 0) + 1 }))} />
            <FinalStepsChecklist manuscriptId={manuscriptId} checklist={data.checklist} />
          </div>
          <SourcePane
            key={path}
            manuscriptId={manuscriptId}
            path={path}
            errors={errors}
            jumpTo={jump}
            compiling={compiling}
            compileError={compile.error ? manuscriptFailure(compile.error) : null}
            onCompile={() => compile.mutate(manuscriptId)}
            onText={onText}
            onState={onState}
            registerFlush={registerFlush}
          />
          <div className="relative min-h-0 border-l border-glass-border">
            <PanelResizeHandle limits={MANUSCRIPT_PDF} width={clamped} onWidthChange={setPdfWidth} label="Resize PDF" />
            <PdfPane manuscript={data} width={clamped} />
          </div>
        </div>
      )}
      <HistoryDialog manuscriptId={manuscriptId} open={historyOpen} onOpenChange={setHistoryOpen} onRestored={() => { setLive({}); setHistoryOpen(false) }}
        beforeRestore={async () => (await flushRef.current?.()) ?? true} />
    </AppShell>
  )
}
