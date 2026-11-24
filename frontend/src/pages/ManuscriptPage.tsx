import { FolderInput, History, Trash2 } from 'lucide-react'
import { DownloadMenu } from '@/features/manuscripts/DownloadMenu'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useCompileManuscript, useManuscript, useManuscriptPapers, useManuscriptRequests, usePapersFollowCompile, usePinPaper } from '@/services/queries'
import { AppShell } from '@/layout/AppShell'
import { Button } from '@/components/ui/button'
import { LoadError } from '@/components/ErrorAlert'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { manuscriptHref, workspaceHref } from '@/router/route'
import { errorsFor } from '@/features/manuscripts/compileErrors'
import { manuscriptFailure } from '@/features/manuscripts/errors'
import { DeleteManuscriptDialog, MoveManuscriptDialog } from '@/features/manuscripts/ManuscriptDialogs'
import { HistoryDialog } from '@/features/manuscripts/HistoryDialog'
import { Breadcrumb } from '@/features/manuscripts/Breadcrumb'
import { crumbsAt } from '@/features/manuscripts/outline'
import { SectionsColumn } from '@/features/manuscripts/SectionsColumn'
import { DeckColumn } from '@/features/manuscripts/deck/DeckColumn'
import { StudioColumns } from '@/features/manuscripts/StudioColumns'
import { CheckPanel } from '@/features/manuscripts/CheckPanel'
import { PdfPane } from '@/features/manuscripts/PdfPane'
import { PdfEditBox } from '@/features/manuscripts/PdfEditBox'
import { MANUSCRIPT_PAPERS, MANUSCRIPT_PDF, MANUSCRIPT_SECTIONS } from '@/features/manuscripts/pdfPanel'
import { keptTexts } from '@/features/manuscripts/keptTexts'
import { KeptTextAlert } from '@/features/manuscripts/KeptTextAlert'
import { JumpPalette } from '@/features/manuscripts/JumpPalette'
import { useInsertBlock } from '@/features/manuscripts/results/useInsertBlock'
import { SourcePane } from '@/features/manuscripts/SourcePane'
import { useUnsavedTexts } from '@/features/manuscripts/useUnsavedTexts'
import { useStudioLinks } from '@/features/manuscripts/useStudioLinks'
import { useStudioCommands } from '@/features/manuscripts/useStudioCommands'
import { useManuscriptTexts } from '@/features/manuscripts/useManuscriptTexts'
import { usePdfSync } from '@/features/manuscripts/usePdfSync'
import { usePdfEdit } from '@/features/manuscripts/usePdfEdit'
import { useStudioNavigation } from '@/features/manuscripts/useStudioNavigation'

/** The writing studio: files and outline | source | PDF. `file` is the `?file=` of the route; null is the main file. */
export function ManuscriptPage({ manuscriptId, file, line = null }: { manuscriptId: string; file: string | null; line?: number | null }) {
  const manuscript = useManuscript(manuscriptId)
  const requests = useManuscriptRequests(manuscriptId)
  const libraryPapers = useManuscriptPapers(manuscriptId)
  const pin = usePinPaper()
  const pinPaper = useCallback((paperId: string) => pin.mutate({ id: manuscriptId, paperId }), [pin.mutate, manuscriptId]) // eslint-disable-line react-hooks/exhaustive-deps
  const compile = useCompileManuscript()
  const data = manuscript.data
  usePapersFollowCompile(manuscriptId, data?.compiled_at)
  const [jump, setJump] = useState<{ line: number; n: number } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [dialog, setDialog] = useState<'move' | 'delete' | null>(null)
  const { kept, savedTick, onState, flushRef, flushCurrent, registerFlush } = useUnsavedTexts(manuscriptId)
  const {
    replaceRef, registerReplace, registerInsert, hasEditor, insertAtCursor, registerFindEvidence, findFromDeck,
    openKey, evidenceAsk, reveal, showCited, findEvidence, clearEvidence, revealPdf,
  } = useStudioLinks()
  const { paletteOpen, setPaletteOpen, sectionAsk, ask } = useStudioCommands()
  const [cursor, setCursor] = useState<{ path: string; line: number } | null>(null)
  const path = data && (file && data.files.some((f) => f.path === file) ? file : data.main_file)
  const { onText, setLive, fileTexts, allTexts, section, items, rows } = useManuscriptTexts(manuscriptId, data, path, cursor)
  const textsRef = useRef(fileTexts)
  textsRef.current = fileTexts
  const cursorLine = cursor && cursor.path === path ? cursor.line : 1 // a cursor belongs to the file it is in
  const errors = useMemo(() => (path && data ? errorsFor(data.compile_errors, path) : []), [data?.compile_errors, path])
  const isOwn = (f: string) => data?.files.some((x) => x.path === f) ?? false

  useEffect(() => setJump(path === file && line ? { line, n: 1 } : null), [path, file, line]) // a jump belongs to the file it was made in; ?line= starts one

  const { target, stillStamp, showInPdf, sourceAt, latest, setEditCompile } = usePdfSync({ manuscriptId, requests, data, path, line, cursor, setJump, isOwn })
  const { edit, setEdit, editAt, saveEdit } = usePdfEdit({ manuscriptId, requests, data, path, latest, isOwn, textsRef, replaceRef, flushCurrent, compile, setEditCompile })
  const compiling = compile.isPending || data?.compile_status === 'running' || data?.compile_requested === true
  const { jumpTo, targets, singleFile, pick, openSection, stepSection } = useStudioNavigation({
    manuscriptId, data, path, cursorLine, rows, items, fileTexts, papers: libraryPapers.data, setJump, showInPdf, showCited,
  })
  const insertBlock = useInsertBlock({
    manuscriptId, mainFile: data?.main_file ?? null, openPath: path ?? null, getText: (p) => textsRef.current[p],
    hasEditor, insert: insertAtCursor,
  })

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
          <DownloadMenu manuscript={data} />
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
                  <SectionsColumn
                    manuscriptId={manuscriptId}
                    data={data}
                    path={path}
                    cursorLine={cursorLine}
                    fileTexts={fileTexts}
                    items={items}
                    sectionAsk={sectionAsk}
                    flushCurrent={flushCurrent}
                    jumpTo={jumpTo}
                    openSection={openSection}
                  />
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
                    onShowInPdf={(ln) => { showInPdf(path, ln); revealPdf() }}
                    onText={onText}
                    onState={onState}
                    registerFlush={registerFlush}
                    registerReplace={registerReplace}
                    registerInsert={registerInsert}
                    onInsertBlock={insertBlock}
                    labelTexts={() => Object.values(textsRef.current)}
                    filePaths={() => data.files.map((f) => f.path)}
                    registerFindEvidence={registerFindEvidence}
                    onCiteKey={showCited}
                    onFindEvidence={findEvidence}
                    workspaceId={data.workspace_id}
                    citeOptions={libraryPapers.data}
                    onCite={pinPaper}
                  />
                ),
              },
              { id: 'pdf', label: 'PDF', limits: MANUSCRIPT_PDF, shareWith: 'papers', content: (width) => <div className="flex h-full min-h-0 flex-col"><div className="min-h-0 flex-1"><PdfPane manuscript={data} width={width} target={target} stillStamp={stillStamp} onSourceAt={sourceAt} onEditAt={editAt}>
                {edit && (
                  <PdfEditBox
                    key={edit.id}
                    anchor={edit.anchor}
                    initial={edit.initial}
                    notice={edit.notice ?? (edit.at ? undefined : 'This text is made by LaTeX (a citation, a number or the reference list).')}
                    onSave={saveEdit}
                    onCancel={() => setEdit(null)}
                    onOpenSource={edit.generated ? undefined : () => { jumpTo(edit.file, edit.line); setEdit(null) }}
                  />
                )}
              </PdfPane></div><CheckPanel manuscriptId={manuscriptId} savedTick={savedTick} compiledAt={data?.compiled_at} onJump={jumpTo} /></div> },
              {
                id: 'papers',
                label: 'Papers',
                limits: MANUSCRIPT_PAPERS,
                content: <DeckColumn manuscriptId={manuscriptId} sectionKey={section.key} sectionText={section.text} allTexts={allTexts} onInsert={insertAtCursor} openKey={openKey} evidenceAsk={evidenceAsk} onFindEvidence={findFromDeck} onClearEvidence={clearEvidence} />,
              },
            ]}
            reveal={reveal ?? undefined}
          />
        </>
      )}
      {data && path && (
        <JumpPalette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          targets={targets}
          onPick={pick}
          commands={[
            { id: 'compile', label: 'Compile', run: () => compile.mutate(manuscriptId) },
            { id: 'new', label: 'New section', run: () => ask('new') },
            ...(singleFile ? [{ id: 'split', label: 'Split into files', run: () => ask('split') }] : []),
            { id: 'pdf', label: 'Show in PDF', run: () => { showInPdf(path, cursorLine); revealPdf() } },
          ]}
        />
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
