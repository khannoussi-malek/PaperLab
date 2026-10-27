import { useQueries } from '@tanstack/react-query'
import { Download, FolderInput, History, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/api/client'
import { useCompileManuscript, useManuscript } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/button'
import { LoadError } from '@/features/library/ErrorAlert'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { manuscriptHref, workspaceHref } from '@/lib/route'
import { errorsFor, parseCompileErrors } from './compileErrors'
import { manuscriptFailure } from './errors'
import { FileList } from './FileList'
import { FinalStepsChecklist } from './FinalStepsChecklist'
import { DeleteManuscriptDialog, MoveManuscriptDialog } from './ManuscriptDialogs'
import { HistoryDialog } from './HistoryDialog'
import { Breadcrumb } from './Breadcrumb'
import { crumbsAt, outline } from './outline'
import { SectionList } from './SectionList'
import { openRowIndex, sectionRows, type SectionRow } from './sections'
import { StudioColumns } from './StudioColumns'
import { PdfPane } from './PdfPane'
import { MANUSCRIPT_PDF, MANUSCRIPT_SECTIONS } from './pdfPanel'
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
  const [dialog, setDialog] = useState<'move' | 'delete' | null>(null)
  const kept = useKeptTexts(manuscriptId) // text a closed file could not save; lives outside the page
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({})
  const flushRef = useRef<(() => Promise<boolean>) | null>(null)
  useLeaveWarning(Object.values(saveStates).some((s) => s !== 'saved')) // kept texts are warned about in App
  const onText = useCallback(
    (p: string, text: string | null) =>
      setLive((l) => (text === null ? Object.fromEntries(Object.entries(l).filter(([k]) => k !== p)) : { ...l, [p]: text })),
    [],
  )
  const flushCurrent = useCallback(async () => (await flushRef.current?.()) ?? true, [])
  const [cursor, setCursor] = useState<{ path: string; line: number } | null>(null)
  const onState = useCallback((p: string, s: SaveState) => setSaveStates((all) => ({ ...all, [p]: s })), [])
  const registerFlush = useCallback((f: (() => Promise<boolean>) | null) => { flushRef.current = f }, [])

  const path = data && (file && data.files.some((f) => f.path === file) ? file : data.main_file)
  // Same keys as the editor's own query, so the open file is fetched once; the others feed the outline.
  const texFiles = (data?.files ?? []).filter((f) => f.path.endsWith('.tex'))
  const texQueries = useQueries({
    queries: texFiles.map((f) => ({ queryKey: ['manuscripts', manuscriptId, 'file', f.path], queryFn: () => api.getManuscriptFile(manuscriptId, f.path) })),
  })
  const texts = texQueries.map((q) => q.data?.text).join('\u0000')
  const fileTexts = useMemo(() => {
    const files = Object.fromEntries(texFiles.flatMap((f, i) => (texQueries[i].data ? [[f.path, texQueries[i].data.text]] : [])))
    return { ...files, ...live }
  }, [texts, live])
  const items = useMemo(() => (data ? outline(fileTexts, data.main_file) : []), [data?.main_file, fileTexts])
  const errorsByFile = useMemo(
    () => parseCompileErrors(data?.compile_errors).reduce<Record<string, number>>((n, e) => ({ ...n, [e.file]: (n[e.file] ?? 0) + 1 }), {}),
    [data?.compile_errors],
  )
  const errors = useMemo(() => (path && data ? errorsFor(data.compile_errors, path) : []), [data?.compile_errors, path])

  useEffect(() => setJump(null), [path]) // a jump belongs to the file it was made in

  const compiling = compile.isPending || data?.compile_status === 'running' || data?.compile_requested === true
  const cursorLine = cursor && cursor.path === path ? cursor.line : 1 // a cursor belongs to the file it is in
  const jumpTo = (f: string, line: number) => {
    if (f === path) setJump((j) => ({ line, n: (j?.n ?? 0) + 1 }))
    else window.location.assign(manuscriptHref(manuscriptId, f))
  }
  const openSection = (row: SectionRow) => jumpTo(row.path, row.inMain ? row.line : 1)
  const stepSection = (step: -1 | 1) => {
    if (!data || !path) return
    const rows = sectionRows(fileTexts, data.main_file, new Set(data.files.map((f) => f.path)))
    const at = openRowIndex(rows, path, cursorLine)
    const next = rows[at === -1 && step === 1 ? 0 : at + step]
    if (next && !next.missing) openSection(next)
  }

  return (
    <AppShell
      fills
      title={data?.title ?? 'Manuscript'}
      back={data?.workspace_id ? { href: workspaceHref(data.workspace_id, 'write'), label: 'Back to workspace' } : undefined}
      actions={data && (
        <>
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}><History aria-hidden />History</Button>
          <Button variant="ghost" size="sm" onClick={() => setDialog('move')}><FolderInput aria-hidden />Move</Button>
          <Button variant="ghost" size="sm" onClick={() => setDialog('delete')}><Trash2 aria-hidden />Delete</Button>
          <Button variant="ghost" size="sm" asChild>
            <a href={api.manuscriptExportUrl(manuscriptId)} download><Download aria-hidden />Download zip</a>
          </Button>
        </>
      )}
    >
      {manuscript.error && <LoadError message={manuscript.error.message} onRetry={() => void manuscript.refetch()} />}
      {manuscript.isPending && <TabSkeleton label="Loading manuscript" />}
      {kept.filter((k) => k.path !== path).map((k) => (
        <KeptTextAlert
          key={k.id}
          path={k.path}
          kept={k}
          action={<Button size="sm" variant="outline" asChild><a href={manuscriptHref(manuscriptId, k.path)}>Open it</a></Button>}
          onDiscard={() => keptTexts.remove(k.id)}
        />
      ))}
      {data && path && (
        <>
          <Breadcrumb crumbs={crumbsAt(items, path, cursorLine)} onJump={jumpTo} />
          <StudioColumns
            columns={[
              {
                id: 'sections',
                label: 'Sections',
                limits: MANUSCRIPT_SECTIONS,
                content: (
                  <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto py-2">
                    <SectionList
                      manuscriptId={manuscriptId}
                      main={data.main_file}
                      texts={fileTexts}
                      filePaths={data.files.map((f) => f.path)}
                      errorsByFile={errorsByFile}
                      current={{ path, line: cursorLine }}
                      items={items}
                      flushCurrent={flushCurrent}
                      onOpen={openSection}
                      onJump={jumpTo}
                    />
                    <details className="px-0">
                      <summary className="cursor-pointer px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">All files</summary>
                      <FileList manuscriptId={manuscriptId} files={data.files} current={path} main={data.main_file} flushCurrent={flushCurrent} />
                    </details>
                    <FinalStepsChecklist manuscriptId={manuscriptId} checklist={data.checklist} />
                  </div>
                ),
              },
              {
                id: 'editor',
                label: 'Editor',
                content: (
                  <SourcePane
                    key={path}
                    manuscriptId={manuscriptId}
                    path={path}
                    errors={errors}
                    jumpTo={jump}
                    compiling={compiling}
                    compileError={compile.error ? manuscriptFailure(compile.error) : null}
                    onCompile={() => compile.mutate(manuscriptId)}
                    onCursor={(line) => setCursor({ path, line })}
                    onSectionStep={stepSection}
                    onText={onText}
                    onState={onState}
                    registerFlush={registerFlush}
                  />
                ),
              },
              { id: 'pdf', label: 'PDF', limits: MANUSCRIPT_PDF, content: (width) => <PdfPane manuscript={data} width={width} /> },
            ]}
          />
        </>
      )}
      {data && (
        <>
          <MoveManuscriptDialog manuscript={data} open={dialog === 'move'} onOpenChange={(o) => setDialog(o ? 'move' : null)} />
          <DeleteManuscriptDialog manuscript={data} open={dialog === 'delete'} onOpenChange={(o) => setDialog(o ? 'delete' : null)}
            onDeleted={() => window.location.assign(data.workspace_id ? workspaceHref(data.workspace_id, 'write') : '#/')} />
        </>
      )}
      <HistoryDialog manuscriptId={manuscriptId} open={historyOpen} onOpenChange={setHistoryOpen} onRestored={() => { setLive({}); setHistoryOpen(false) }}
        beforeRestore={async () => (await flushRef.current?.()) ?? true} />
    </AppShell>
  )
}
