import { useQueries } from '@tanstack/react-query'
import { Download, FolderInput, History, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '@/api/client'
import { useCompileManuscript, useManuscript, useManuscriptPapers, usePapersFollowCompile, usePinPaper } from '@/api/queries'
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
import { openRowIndex, sectionRows, sectionText, type SectionRow } from './sections'
import { DeckColumn } from './deck/DeckColumn'
import { StudioColumns } from './StudioColumns'
import { PdfPane, type PdfTarget } from './PdfPane'
import { PdfEditBox } from './PdfEditBox'
import { findEditable, type Span } from './pdfEdit'
import { MANUSCRIPT_PAPERS, MANUSCRIPT_PDF, MANUSCRIPT_SECTIONS } from './pdfPanel'
import type { SaveState } from './autosave'
import { keptTexts, useKeptTexts } from './keptTexts'
import { KeptTextAlert } from './KeptTextAlert'
import { JumpPalette } from './JumpPalette'
import { jumpTargets, type Target } from './jumpTargets'
import { SourcePane } from './SourcePane'
import { useLeaveWarning } from './useLeaveWarning'

/** The writing studio: files and outline | source | PDF. `file` is the `?file=` of the route; null is the main file. */
export function ManuscriptPage({ manuscriptId, file, line = null }: { manuscriptId: string; file: string | null; line?: number | null }) {
  const manuscript = useManuscript(manuscriptId)
  const libraryPapers = useManuscriptPapers(manuscriptId)
  const pin = usePinPaper()
  const pinPaper = useCallback((paperId: string) => pin.mutate({ id: manuscriptId, paperId }), [pin.mutate, manuscriptId]) // eslint-disable-line react-hooks/exhaustive-deps
  const compile = useCompileManuscript()
  const data = manuscript.data
  usePapersFollowCompile(manuscriptId, data?.compiled_at)
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
  const replaceRef = useRef<((line: number, start: number, end: number, text: string) => void) | null>(null)
  const registerReplace = useCallback((f: typeof replaceRef.current) => { replaceRef.current = f }, [])
  const insertRef = useRef<((text: string) => void) | null>(null)
  const registerInsert = useCallback((f: typeof insertRef.current) => { insertRef.current = f }, [])
  const findRef = useRef<(() => boolean) | null>(null)
  const registerFindEvidence = useCallback((f: typeof findRef.current) => { findRef.current = f }, [])
  const findFromDeck = useCallback(() => findRef.current?.() ?? false, [])
  const insertAtCursor = useCallback((text: string) => {
    if (!insertRef.current) return false
    insertRef.current(text)
    return true
  }, [])
  const [openKey, setOpenKey] = useState<{ key: string; n: number } | null>(null)
  const [evidenceAsk, setEvidenceAsk] = useState<{ doc: string; from: number; to: number; n: number } | null>(null)
  const [reveal, setReveal] = useState<{ id: string; n: number } | null>(null)
  const showCited = useCallback((key: string) => {
    setOpenKey((k) => ({ key, n: (k?.n ?? 0) + 1 }))
    setReveal((r) => ({ id: 'papers', n: (r?.n ?? 0) + 1 }))
  }, [])
  const asks = useRef(0) // never restarts, so an ask after Clear is never mistaken for one the deck already ran
  const findEvidence = useCallback((doc: string, from: number, to: number) => {
    setEvidenceAsk({ doc, from, to, n: ++asks.current })
    setReveal((r) => ({ id: 'papers', n: (r?.n ?? 0) + 1 }))
  }, [])
  const clearEvidence = useCallback(() => setEvidenceAsk(null), []) // a remounted deck must not ask it again
  // Only an explicit Show in PDF brings the PDF forward (its tab, when it shares one with Papers); following a compile never does.
  const revealPdf = useCallback(() => setReveal((r) => ({ id: 'pdf', n: (r?.n ?? 0) + 1 })), [])
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sectionAsk, setSectionAsk] = useState<{ kind: 'new' | 'split'; n: number } | null>(null)
  useEffect(() => { // Cmd/Ctrl+K anywhere in the studio; CodeMirror leaves it alone, so it bubbles up from the editor too
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'k' || !(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.defaultPrevented) return
      if (document.querySelector('[role=dialog][data-state=open]')) return // History, Move, Delete or the palette itself
      e.preventDefault()
      setPaletteOpen(true)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
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
  const allTexts = useMemo(() => Object.values(fileTexts), [fileTexts])
  // The section being written (its key changes when another one is opened), for the deck's order and ranking.
  const section = useMemo(() => {
    if (!data || !path) return { key: '', text: '' }
    const rows = sectionRows(fileTexts, data.main_file, new Set(data.files.map((f) => f.path)))
    const row = rows[openRowIndex(rows, path, cursor && cursor.path === path ? cursor.line : 1)]
    return row && !row.missing ? { key: `${row.path}:${row.line}`, text: sectionText(fileTexts, row) } : { key: path, text: fileTexts[path] ?? '' }
  }, [fileTexts, data, path, cursor])
  const items = useMemo(() => (data ? outline(fileTexts, data.main_file) : []), [data?.main_file, fileTexts])
  const errorsByFile = useMemo(
    () => parseCompileErrors(data?.compile_errors).reduce<Record<string, number>>((n, e) => ({ ...n, [e.file]: (n[e.file] ?? 0) + 1 }), {}),
    [data?.compile_errors],
  )
  const errors = useMemo(() => (path && data ? errorsFor(data.compile_errors, path) : []), [data?.compile_errors, path])

  useEffect(() => setJump(path === file && line ? { line, n: 1 } : null), [path, file, line]) // a jump belongs to the file it was made in; ?line= starts one

  const [target, setTarget] = useState<PdfTarget | null>(null)
  const latest = useRef({ path, line: line ?? 1 })
  latest.current = { path, line: cursor && cursor.path === path ? cursor.line : (line ?? 1) }
  // Best effort and silent: no index, no match or no network just leaves the PDF where it is.
  const forwardId = useRef(0) // only the newest forward lookup may move the PDF
  const inverseId = useRef(0)
  const showInPdf = useCallback((f: string, ln: number) => {
    const id = ++forwardId.current
    api.syncForward(manuscriptId, f, ln).then((r) => { if (id === forwardId.current) setTarget((t) => ({ page: r.page, y: r.y, n: (t?.n ?? 0) + 1 })) }, () => {})
  }, [manuscriptId])
  const goodStamp = data?.compile_status === 'ok' ? data.compiled_at : null
  // A compile started by an edit from the PDF keeps the PDF where it is. `editCompile` holds compiled_at when it
  // started; once a compile is stored after that, a good one's stamp becomes `stillStamp`: no forward lookup for it,
  // and PdfPane leaves its PDF at the scroll it has. Set during render, so the PDF and the stamp arrive together.
  const [editCompile, setEditCompile] = useState<{ from: string | null } | null>(null)
  const [stillStamp, setStillStamp] = useState<string | null>(null)
  if (editCompile && data && data.compiled_at !== editCompile.from) {
    if (goodStamp) setStillStamp(goodStamp)
    setEditCompile(null)
  }
  const seenStamp = useRef<string | null>(null)
  useEffect(() => { // once per new good compile, and when a file opens on one; never per cursor move
    const fresh = goodStamp !== seenStamp.current
    seenStamp.current = goodStamp
    if (fresh && goodStamp && goodStamp === stillStamp) return // the compile of an edit from the PDF
    if (goodStamp && latest.current.path) showInPdf(latest.current.path, latest.current.line)
  }, [goodStamp, path, showInPdf, stillStamp])

  const compiling = compile.isPending || data?.compile_status === 'running' || data?.compile_requested === true
  const cursorLine = cursor && cursor.path === path ? cursor.line : 1 // a cursor belongs to the file it is in
  const jumpTo = (f: string, line: number) => {
    if (f === path) { setJump((j) => ({ line, n: (j?.n ?? 0) + 1 })); showInPdf(f, line) }
    else window.location.assign(manuscriptHref(manuscriptId, f, line))
  }
  const isOwn = (f: string) => data?.files.some((x) => x.path === f) ?? false
  const sourceAt = (page: number, x: number, y: number) => {
    const id = ++inverseId.current
    const from = path
    api.syncInverse(manuscriptId, page, x, y).then((r) => {
      if (id !== inverseId.current || from !== latest.current.path) return // a newer click, or another file opened meanwhile
      if (!isOwn(r.file)) return // made by LaTeX (main.bbl): nothing of the user's to open
      if (r.file === path) setJump((j) => ({ line: r.line, n: (j?.n ?? 0) + 1 }))
      else window.location.assign(manuscriptHref(manuscriptId, r.file, r.line))
    }, () => {})
  }
  // Edit from the PDF: the sentence behind a double-clicked word, or a note that LaTeX made it.
  const [edit, setEdit] = useState<{ id: number; anchor: DOMRect; file: string; line: number; at: Span | null; initial: string; notice?: string; generated?: boolean } | null>(null)
  const editId = useRef(0)
  const textsRef = useRef(fileTexts)
  textsRef.current = fileTexts
  const editAt = (page: number, x: number, y: number, word: string, anchor: DOMRect) => {
    const id = ++editId.current
    const from = path
    void (async () => {
      const r = await api.syncInverse(manuscriptId, page, x, y)
      if (id !== editId.current || from !== latest.current.path) return // a newer double-click, or another file opened meanwhile
      if (!isOwn(r.file)) { // a file LaTeX wrote (main.bbl): nothing to edit or open
        setEdit({ id, anchor, file: r.file, line: r.line, at: null, initial: '', generated: true })
        return
      }
      let text: string | undefined = r.file === from ? textsRef.current[r.file] : undefined // the editor's buffer when it is open
      if (text === undefined) {
        const fresh = await api.getManuscriptFile(manuscriptId, r.file)
        if (id !== editId.current || from !== latest.current.path) return
        text = fresh.text
      }
      const lines = text.split('\n')
      const whole = lines[r.line - 1] === undefined ? null : { line: r.line, start: 0, end: lines[r.line - 1].length }
      const at = word ? findEditable(lines, r.line, word) : whole // E on the pane has no word: the whole SyncTeX line
      setEdit({ id, anchor, file: r.file, line: r.line, at, initial: at ? lines[at.line - 1].slice(at.start, at.end) : '' })
    })().catch(() => {}) // no index or no network: stay quiet
  }
  const saveEdit = async (replacement: string) => {
    if (!edit?.at) return
    const { file: target, at, initial } = edit
    const changed = new Error('This file changed since. Open it in the editor to edit it.')
    if (target === latest.current.path) {
      const now = textsRef.current[target]?.split('\n')[at.line - 1]?.slice(at.start, at.end)
      if (now !== initial || !replaceRef.current) throw changed // typed over since the box opened
      replaceRef.current(at.line, at.start, at.end, replacement)
      if (!(await flushCurrent())) { // saved before compiling, so the compile sees it
        // The text is in the editor, so a retry here could never match; the editor shows why it didn't save.
        setEdit({ ...edit, id: ++editId.current, at: null, notice: "Your change is in the editor but couldn't be saved yet. The editor shows why." })
        return
      }
    } else {
      const lines = (await api.getManuscriptFile(manuscriptId, target))
      const row = lines.text.split('\n')
      if (row[at.line - 1]?.slice(at.start, at.end) !== initial) throw changed
      row[at.line - 1] = row[at.line - 1].slice(0, at.start) + replacement + row[at.line - 1].slice(at.end)
      try { await api.saveManuscriptFile(manuscriptId, target, row.join('\n'), lines.updated_at) }
      catch (e) { throw e instanceof ApiError && e.code === 'file_changed' ? changed : e }
    }
    setEdit(null)
    setEditCompile({ from: data?.compiled_at ?? null })
    compile.mutate(manuscriptId, { onError: () => setEditCompile(null) })
  }
  const rows = useMemo(() => (data ? sectionRows(fileTexts, data.main_file, new Set(data.files.map((f) => f.path))) : []), [data, fileTexts])
  const targets = useMemo(() => jumpTargets(rows, items, fileTexts, libraryPapers.data ?? []), [rows, items, fileTexts, libraryPapers.data])
  const singleFile = rows.length > 0 && rows.every((r) => r.inMain)
  const ask = (kind: 'new' | 'split') => setSectionAsk((a) => ({ kind, n: (a?.n ?? 0) + 1 }))
  const pick = (t: Target) => (t.kind === 'paper' ? showCited(t.key) : jumpTo(t.file, t.line))
  const openSection = (row: SectionRow) => jumpTo(row.path, row.inMain ? row.line : 1)
  const stepSection = (step: -1 | 1) => {
    if (!data || !path) return
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
                      request={sectionAsk}
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
                    onShowInPdf={(ln) => { showInPdf(path, ln); revealPdf() }}
                    onText={onText}
                    onState={onState}
                    registerFlush={registerFlush}
                    registerReplace={registerReplace}
                    registerInsert={registerInsert}
                    registerFindEvidence={registerFindEvidence}
                    onCiteKey={showCited}
                    onFindEvidence={findEvidence}
                    citeOptions={libraryPapers.data}
                    onCite={pinPaper}
                  />
                ),
              },
              { id: 'pdf', label: 'PDF', limits: MANUSCRIPT_PDF, shareWith: 'papers', content: (width) => <PdfPane manuscript={data} width={width} target={target} stillStamp={stillStamp} onSourceAt={sourceAt} onEditAt={editAt}>
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
              </PdfPane> },
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
