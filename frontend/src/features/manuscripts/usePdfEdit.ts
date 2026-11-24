import { useRef, useState } from 'react'
import { ApiError } from '@/services/api'
import type { useCompileManuscript, useManuscript, useManuscriptRequests } from '@/services/queries'
import { findEditable, type Span } from '@/features/manuscripts/pdfEdit'
import type { usePdfSync } from '@/features/manuscripts/usePdfSync'

type Data = ReturnType<typeof useManuscript>['data']

/** Edit from the PDF: the box over a double-clicked word, saved into its source line and compiled again. */
export function usePdfEdit({ manuscriptId, requests, data, path, latest, isOwn, textsRef, replaceRef, flushCurrent, compile, setEditCompile }: {
  manuscriptId: string
  requests: ReturnType<typeof useManuscriptRequests>
  data: Data
  path: string | undefined
  latest: ReturnType<typeof usePdfSync>['latest']
  isOwn: (f: string) => boolean
  textsRef: { current: Record<string, string> }
  replaceRef: { current: ((line: number, start: number, end: number, text: string) => void) | null }
  flushCurrent: () => Promise<boolean>
  compile: ReturnType<typeof useCompileManuscript>
  setEditCompile: ReturnType<typeof usePdfSync>['setEditCompile']
}) {
  // Edit from the PDF: the sentence behind a double-clicked word, or a note that LaTeX made it.
  const [edit, setEdit] = useState<{ id: number; anchor: DOMRect; file: string; line: number; at: Span | null; initial: string; notice?: string; generated?: boolean } | null>(null)
  const editId = useRef(0)
  const editAt = (page: number, x: number, y: number, word: string, anchor: DOMRect) => {
    const id = ++editId.current
    const from = path
    void (async () => {
      const r = await requests.syncInverse(page, x, y)
      if (id !== editId.current || from !== latest.current.path) return // a newer double-click, or another file opened meanwhile
      if (!isOwn(r.file)) { // a file LaTeX wrote (main.bbl): nothing to edit or open
        setEdit({ id, anchor, file: r.file, line: r.line, at: null, initial: '', generated: true })
        return
      }
      let text: string | undefined = r.file === from ? textsRef.current[r.file] : undefined // the editor's buffer when it is open
      if (text === undefined) {
        const fresh = await requests.getFile(r.file)
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
      const lines = await requests.getFile(target)
      const row = lines.text.split('\n')
      if (row[at.line - 1]?.slice(at.start, at.end) !== initial) throw changed
      row[at.line - 1] = row[at.line - 1].slice(0, at.start) + replacement + row[at.line - 1].slice(at.end)
      try { await requests.saveFile(target, row.join('\n'), lines.updated_at) }
      catch (e) { throw e instanceof ApiError && e.code === 'file_changed' ? changed : e }
    }
    setEdit(null)
    setEditCompile({ from: data?.compiled_at ?? null })
    compile.mutate(manuscriptId, { onError: () => setEditCompile(null) })
  }
  return { edit, setEdit, editAt, saveEdit }
}
