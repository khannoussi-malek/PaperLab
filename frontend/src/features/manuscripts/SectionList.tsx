import { FilePlus, MoreHorizontal } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useAddSection, useDeleteSection, useMoveSection, useRetitleSection, useSplitSections } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { manuscriptHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { manuscriptFailure } from './errors'
import type { OutlineItem } from './outline'
import { DeleteSectionDialog, SectionTitleDialog } from './SectionDialogs'
import { openRowIndex, sectionRows, sectionText, wordCount, type SectionRow } from './sections'
import { sectionStatus, type SectionStatus } from './sectionStatus'

const DOT: Record<SectionStatus, string> = {
  empty: 'bg-muted-foreground/50',
  error: 'bg-destructive',
  todo: 'bg-amber-500',
  ok: 'bg-emerald-600',
}
const ROW = 'flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50'

type Props = {
  manuscriptId: string
  main: string
  /** Text of every loaded .tex file, unsaved typing included. */
  texts: Record<string, string>
  /** Every file path of the manuscript; one of these without text is still loading, not missing. */
  filePaths: readonly string[]
  /** Compile errors per file. */
  errorsByFile: Record<string, number>
  current: { path: string; line: number }
  items: OutlineItem[]
  onOpen: (row: SectionRow) => void
  onJump: (file: string, line: number) => void
  /** Saves the open file's pending text; false when it could not, so nothing is rewritten under it. */
  flushCurrent: () => Promise<boolean>
  /** The palette asks for the New section dialog or a split; a new `n` asks again. */
  request?: { kind: 'new' | 'split'; n: number } | null
}
type Dlg = { kind: 'new'; after: string | null } | { kind: 'rename' | 'delete'; row: SectionRow } | null

/** The paper as a list of sections: number, title, words and a status dot; new, rename, reorder, delete, split. */
export function SectionList({ manuscriptId, main, texts, filePaths, errorsByFile, current, items, onOpen, onJump, flushCurrent, request }: Props) {
  const add = useAddSection()
  const split = useSplitSections()
  const retitle = useRetitleSection()
  const move = useMoveSection()
  const remove = useDeleteSection()
  const [dlg, setDlg] = useState<Dlg>(null)
  const [error, setError] = useState<string | null>(null)
  const buttons = useRef(new Map<string, HTMLButtonElement>())
  const refocus = useRef<string | null>(null)
  const rows = sectionRows(texts, main, new Set(filePaths))
  const busy = add.isPending || split.isPending || retitle.isPending || move.isPending || remove.isPending
  const singleFile = rows.length > 0 && rows.every((r) => r.inMain)
  const key = (r: SectionRow) => `${r.path}:${r.line}`
  const openRow = rows[openRowIndex(rows, current.path, current.line)]

  useEffect(() => { // a moved row keeps the keyboard focus
    if (refocus.current) buttons.current.get(refocus.current)?.focus()
    refocus.current = null
  }, [rows.map(key).join('|')]) // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => { setDlg(null); setError(null) }
  const onError = (e: Error) => setError(manuscriptFailure(e))
  const go = (path: string) => window.location.assign(manuscriptHref(manuscriptId, path))
  // Every operation saves the open editor first and stops if that fails (the editor shows why).
  const working = useRef(false) // one operation at a time, flush included
  const run = async (op: () => void, onFlushFailed?: () => void) => {
    if (working.current) return
    working.current = true
    try {
      setError(null)
      if (await flushCurrent()) op()
      else onFlushFailed?.()
    } finally { working.current = false }
  }

  const addSection = (title: string, after: string | null) =>
    run(() => add.mutate({ id: manuscriptId, title, after }, { onSuccess: (r) => { close(); go(r.path) }, onError }))
  const rename = (row: SectionRow, title: string) =>
    run(() => retitle.mutate({ id: manuscriptId, path: row.path, title }, { onSuccess: (r) => { close(); go(r.path) }, onError }))
  const del = (row: SectionRow) =>
    run(() => remove.mutate({ id: manuscriptId, path: row.path }, { onSuccess: () => { close(); if (row.path === current.path) go(main) }, onError }))
  const moveTo = (row: SectionRow, to: number) => {
    if (to < 0 || to >= rows.length) return
    void run(() => move.mutate({ id: manuscriptId, path: row.path, to }, { onSuccess: () => { refocus.current = key(row) }, onError }))
  }
  const splitFiles = () => run(() => split.mutate(manuscriptId, { onError }))

  const asked = useRef(0)
  useEffect(() => {
    if (!request || request.n === asked.current) return
    asked.current = request.n
    if (request.kind === 'new') { setError(null); setDlg({ kind: 'new', after: null }) }
    else if (singleFile) void splitFiles()
  }) // eslint-disable-line react-hooks/exhaustive-deps

  const onKeyDown = (e: React.KeyboardEvent, row: SectionRow, i: number) => {
    if (!(e.target as HTMLElement).closest('[data-section-row]')) return
    const focusAt = (j: number) => { const r = rows[j]; if (r) buttons.current.get(key(r))?.focus() }
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault()
      if (!row.inMain && !row.missing) moveTo(row, e.key === 'ArrowUp' ? i - 1 : i + 1)
    } else if (e.metaKey || e.ctrlKey || e.altKey) return
    else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); focusAt(i + (e.key === 'ArrowUp' ? -1 : 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); onOpen(row) }
    else if (e.key === 'n' || e.key === 'N') { e.preventDefault(); setError(null); setDlg({ kind: 'new', after: row.inMain ? null : row.path }) }
    else if (e.key === 'F2' && !row.inMain) { e.preventDefault(); setError(null); setDlg({ kind: 'rename', row }) }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && !row.inMain) { e.preventDefault(); setError(null); setDlg({ kind: 'delete', row }) }
  }

  const common = { open: true, onOpenChange: (o: boolean) => { if (!o) close() }, busy, error }
  return (
    <nav aria-label="Sections">
      <div className="flex items-center justify-between px-2 pb-1">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sections</h2>
        <Button variant="ghost" size="icon-xs" aria-label="New section" title="New section" onClick={() => { setError(null); setDlg({ kind: 'new', after: null }) }}>
          <FilePlus aria-hidden />
        </Button>
      </div>
      {error && !dlg && <Alert variant="destructive" className="mx-2 mb-1 w-auto"><AlertDescription>{error}</AlertDescription></Alert>}
      {rows.length === 0 && texts[main] === undefined ? (
        <p className="px-2 text-sm text-muted-foreground">Loading sections…</p>
      ) : rows.length === 0 ? (
        <p className="px-2 text-sm text-muted-foreground">No sections yet. Add the first one.</p>
      ) : (
        <ul className="flex flex-col">
          {rows.map((row, i) => {
            const text = sectionText(texts, row)
            const pending = !row.missing && texts[row.path] === undefined
            const st = row.missing || pending ? null : sectionStatus(text, row.inMain ? 0 : (errorsByFile[row.path] ?? 0)) // ponytail: rows inside main.tex show no compile errors
            const subs = row === openRow ? items.filter((it) => it.level > 1 && it.file === row.path && (!row.inMain || it.line > row.line && (rows[i + 1]?.line ?? Infinity) > it.line)) : []
            return (
              <li key={key(row)} onKeyDown={(e) => onKeyDown(e, row, i)}>
                <div className="group flex items-center gap-0.5">
                  <button
                    type="button"
                    data-section-row
                    ref={(el) => { if (el) buttons.current.set(key(row), el); else buttons.current.delete(key(row)) }}
                    aria-current={row === openRow ? 'page' : undefined}
                    title={row.path}
                    className={cn(ROW, row === openRow && 'bg-muted font-medium')}
                    onClick={() => onOpen(row)}
                  >
                    <span className="w-4 shrink-0 text-xs text-muted-foreground">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{row.title}</span>
                    {st ? (
                      <>
                        <span className="shrink-0 text-xs text-muted-foreground">{wordCount(text)} words</span>
                        <span aria-hidden title={st.label} className={cn('size-2 shrink-0 rounded-full', DOT[st.status])} />
                        <span className="sr-only">{st.label}</span>
                      </>
                    ) : pending ? (
                      <span className="shrink-0 text-xs text-muted-foreground">Loading…</span>
                    ) : (
                      <span className="shrink-0 text-xs text-destructive">File missing</span>
                    )}
                  </button>
                  {!row.inMain && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-xs" aria-label={`Actions for ${row.title}`}><MoreHorizontal aria-hidden /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {!row.missing && <DropdownMenuItem onSelect={() => { setError(null); setDlg({ kind: 'rename', row }) }}>Rename</DropdownMenuItem>}
                        <DropdownMenuItem disabled={i === 0} onSelect={() => moveTo(row, i - 1)}>Move up</DropdownMenuItem>
                        <DropdownMenuItem disabled={i === rows.length - 1} onSelect={() => moveTo(row, i + 1)}>Move down</DropdownMenuItem>
                        <DropdownMenuItem variant="destructive" onSelect={() => { setError(null); setDlg({ kind: 'delete', row }) }}>Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
                {subs.length > 0 && (
                  <ul aria-label={`In ${row.title}`}>
                    {subs.map((it) => (
                      <li key={`${it.file}:${it.line}`}>
                        <button type="button" onClick={() => onJump(it.file, it.line)}
                          className={cn(ROW, 'w-full truncate py-0.5 text-xs', it.level === 2 ? 'pl-8' : 'pl-11')}>
                          {it.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {singleFile && (
        <div className="px-2 pt-1">
          <p className="pb-1 text-xs text-muted-foreground">These sections all live in the main file.</p>
          <Button size="xs" variant="outline" disabled={busy} onClick={() => void splitFiles()}>Split into files</Button>
        </div>
      )}
      {dlg?.kind === 'new' && (
        <SectionTitleDialog {...common} heading="New section" hint="It becomes its own file under sections/." initial="" action="Add"
          onSubmit={(t) => void addSection(t, dlg.after)} />
      )}
      {dlg?.kind === 'rename' && (
        <SectionTitleDialog {...common} heading="Rename section" hint="The file is renamed to match." initial={dlg.row.title} action="Rename"
          onSubmit={(t) => void rename(dlg.row, t)} />
      )}
      {dlg?.kind === 'delete' && <DeleteSectionDialog {...common} path={dlg.row.path} onConfirm={() => void del(dlg.row)} />}
    </nav>
  )
}
