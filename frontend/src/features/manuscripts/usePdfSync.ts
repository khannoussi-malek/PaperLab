import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { manuscriptHref } from '@/router/route'
import type { PdfTarget } from '@/features/manuscripts/PdfPane'
import type { useManuscript, useManuscriptRequests } from '@/services/queries'

type Data = ReturnType<typeof useManuscript>['data']
type Requests = ReturnType<typeof useManuscriptRequests>

/** Source to PDF (forward) and PDF to source (inverse) sync, and the stamp of a good compile that keeps the PDF where it is. */
export function usePdfSync({ manuscriptId, requests, data, path, line, cursor, setJump, isOwn }: {
  manuscriptId: string
  requests: Requests
  data: Data
  path: string | undefined
  line: number | null
  cursor: { path: string; line: number } | null
  setJump: Dispatch<SetStateAction<{ line: number; n: number } | null>>
  isOwn: (f: string) => boolean
}) {
  const [target, setTarget] = useState<PdfTarget | null>(null)
  const latest = useRef({ path, line: line ?? 1 })
  latest.current = { path, line: cursor && cursor.path === path ? cursor.line : (line ?? 1) }
  // Best effort and silent: no index, no match or no network just leaves the PDF where it is.
  const forwardId = useRef(0) // only the newest forward lookup may move the PDF
  const inverseId = useRef(0)
  const showInPdf = useCallback((f: string, ln: number) => {
    const id = ++forwardId.current
    requests.syncForward(f, ln).then((r) => { if (id === forwardId.current) setTarget((t) => ({ page: r.page, y: r.y, n: (t?.n ?? 0) + 1 })) }, () => {})
  }, [requests])
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
  const sourceAt = (page: number, x: number, y: number) => {
    const id = ++inverseId.current
    const from = path
    requests.syncInverse(page, x, y).then((r) => {
      if (id !== inverseId.current || from !== latest.current.path) return // a newer click, or another file opened meanwhile
      if (!isOwn(r.file)) return // made by LaTeX (main.bbl): nothing of the user's to open
      if (r.file === path) setJump((j) => ({ line: r.line, n: (j?.n ?? 0) + 1 }))
      else window.location.assign(manuscriptHref(manuscriptId, r.file, r.line))
    }, () => {})
  }
  return { target, stillStamp, showInPdf, sourceAt, latest, setEditCompile }
}
