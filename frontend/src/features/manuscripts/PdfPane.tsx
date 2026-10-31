import { useCallback, useEffect, useRef, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { Download } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { api, type ManuscriptDetail } from '@/api/client'
import { PdfPage } from '../reader/PdfPage'
import { usePdfDocument } from '../reader/usePdfDocument'
import { parseCompileErrors } from './compileErrors'
import { manuscriptErrorMessage } from './errors'

const PAGE_WIDTH_PT = 612
const GUTTERS_PX = 24

export type PdfTarget = { page: number; y: number; n: number }
type Props = {
  manuscript: ManuscriptDetail
  width: number
  /** A point (page 1-based, y in points from the page top) to bring a third of the way down the pane. */
  target: PdfTarget | null
  /** The compile whose PDF stays where it is when it arrives (an edit from the PDF made it), not placed at `target`. */
  stillStamp?: string | null
  /** The source of a PDF spot: ctrl/cmd-click on a page, or Enter for the visible centre. x/y in points. */
  onSourceAt: (page: number, x: number, y: number) => void
  /** A double-click on text, or E for the visible centre (word ''): the page point, the word and where it sits. */
  onEditAt?: (page: number, x: number, y: number, word: string, rect: DOMRect) => void
  /** Overlays positioned within the pane (the edit box). */
  children?: ReactNode
}

/** The compiled PDF, with the compile's errors above it. The pane's width is the parent's, so loading never moves it. */
export function PdfPane({ manuscript: m, width, target, stillStamp, onSourceAt, onEditAt, children }: Props) {
  // The URL carries compiled_at, so each good compile is fetched again. A failed compile also stamps compiled_at but
  // leaves the last PDF on disk, so the URL keeps the last good stamp and that PDF stays on screen.
  const goodAt = useRef<string | null>(null)
  if (m.compile_status === 'ok' && m.compiled_at) goodAt.current = m.compiled_at
  const stamp = goodAt.current ?? m.compiled_at
  const { doc, error } = usePdfDocument(stamp ? api.manuscriptPdfUrl(m.id, stamp) : null)
  const friendly = m.compile_status === 'failed' ? m.compile_friendly : null
  const parsed = parseCompileErrors(m.compile_errors)
  const errors = parsed.filter((e) => e.kind === 'error')
  const missing = parsed.find((e) => e.kind === 'package_missing')?.message // the package the compile named
  const scale = Math.max(0.4, (width - GUTTERS_PX) / PAGE_WIDTH_PT)

  const scroller = useRef<HTMLDivElement>(null)
  const pagesRef = useRef<HTMLDivElement>(null)
  const pending = useRef(false) // a target not yet settled: pages still measuring move it, the user's own scrolling cancels it
  const place = useCallback(() => {
    const box = scroller.current
    const page = box?.querySelector<HTMLElement>(`[data-page="${target?.page}"]`)
    if (!box || !page || !target) return
    box.scrollTop = page.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop + target.y * scale - box.clientHeight / 3
  }, [target, scale])
  const placed = useRef<PdfTarget | null>(null)
  useEffect(() => {
    // A new PDF re-applies the target, except the one an edit from the PDF made: that keeps the scroll it has.
    if (target === placed.current && stamp === stillStamp) { pending.current = false; return }
    placed.current = target
    pending.current = true
    place()
  }, [target, doc]) // eslint-disable-line react-hooks/exhaustive-deps -- not on a resize of the column
  useEffect(() => { // pages learn their real size after mounting; re-apply the target as the stack grows
    const stack = pagesRef.current
    if (!stack || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => { if (pending.current) place() })
    ro.observe(stack)
    return () => ro.disconnect()
  }, [place, doc])
  const report = (el: HTMLElement, x: number, y: number) => {
    const r = el.getBoundingClientRect()
    onSourceAt(Number(el.dataset.page), (x - r.left) / scale, (y - r.top) / scale)
  }
  const click = (e: MouseEvent<HTMLDivElement>) => { if (e.ctrlKey || e.metaKey) report(e.currentTarget, e.clientX, e.clientY) }
  const dblClick = (e: MouseEvent<HTMLDivElement>) => {
    const sel = window.getSelection()
    const word = sel?.toString().trim() ?? ''
    if (!onEditAt || !word) return
    const box = sel && sel.rangeCount > 0 ? sel.getRangeAt(0).getBoundingClientRect?.() : undefined
    const rect = box && (box.width || box.height) ? box : ({ left: e.clientX, right: e.clientX, top: e.clientY, bottom: e.clientY, width: 0, height: 0, x: e.clientX, y: e.clientY } as DOMRect)
    const r = e.currentTarget.getBoundingClientRect()
    onEditAt(Number(e.currentTarget.dataset.page), (e.clientX - r.left) / scale, (e.clientY - r.top) / scale, word, rect)
  }
  /** The visible centre of the pane and the page nearest it. */
  const centre = (pane: HTMLElement) => {
    const r = pane.getBoundingClientRect()
    const cx = r.left + r.width / 2
    const cy = r.top + pane.clientHeight / 2
    const pagesEls = Array.from(pane.querySelectorAll<HTMLElement>('[data-page]'))
    const gap = (p: HTMLElement) => { const b = p.getBoundingClientRect(); return cy < b.top ? b.top - cy : Math.max(0, cy - b.bottom) }
    const hit = pagesEls.reduce<HTMLElement | undefined>((best, p) => (!best || gap(p) < gap(best) ? p : best), undefined)
    return hit && { hit, cx, cy }
  }
  const keyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return
    if (e.key === 'Enter') { // source of the visible centre
      const c = centre(e.currentTarget)
      if (c) { e.preventDefault(); report(c.hit, c.cx, c.cy) }
    } else if ((e.key === 'e' || e.key === 'E') && onEditAt && !e.metaKey && !e.ctrlKey && !e.altKey) { // edit box there
      const c = centre(e.currentTarget)
      if (!c) return
      e.preventDefault()
      // ponytail: no word, so the box holds the whole SyncTeX line; a selection left from an earlier double-click
      // would point at another spot, so it is ignored.
      const p = c.hit.getBoundingClientRect()
      const at = { left: c.cx, right: c.cx, top: c.cy, bottom: c.cy, width: 0, height: 0, x: c.cx, y: c.cy } as DOMRect
      onEditAt(Number(c.hit.dataset.page), (c.cx - p.left) / scale, (c.cy - p.top) / scale, '', at)
    }
  }

  return (
    <section aria-label="PDF preview" className="relative flex h-full min-h-0 flex-col">
      {m.compile_status === 'failed' && (
        <Alert variant="destructive" className="m-2 w-auto">
          <AlertDescription>
            {friendly ? (
              manuscriptErrorMessage(friendly, { name: missing })
            ) : errors.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {errors.map((e, i) => (
                  <li key={i}>{e.file}{e.line ? `:${e.line}` : ''} {e.message}</li>
                ))}
              </ul>
            ) : (
              'The compile failed.'
            )}
            {m.compile_log && !friendly && (
              <details className="mt-2"><summary className="cursor-pointer">Log</summary><pre className="max-h-48 overflow-auto text-xs whitespace-pre-wrap">{m.compile_log}</pre></details>
            )}
          </AlertDescription>
        </Alert>
      )}
      {doc && stamp && (
        <Button variant="secondary" size="icon" asChild className="absolute top-2 right-4 z-10 shadow-sm">
          <a href={api.manuscriptPdfUrl(m.id, stamp)} download={`${m.title}.pdf`} aria-label="Download PDF" title="Download PDF"><Download aria-hidden /></a>
        </Button>
      )}
      <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3" tabIndex={0} aria-label="PDF pages" ref={scroller} onKeyDown={keyDown} onWheel={() => { pending.current = false }} onPointerDown={() => { pending.current = false }}>
        {doc ? (
          <div ref={pagesRef} className="flex flex-col items-center gap-3">
            {Array.from({ length: doc.numPages }, (_, i) => i + 1).map((n) => (
              <div key={n} data-page={n} onClick={click} onDoubleClick={dblClick}><PdfPage doc={doc} pageNumber={n} scale={scale} /></div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {(m.compile_status === 'failed' ? null : error) ?? (m.compile_status === 'running' ? 'Compiling…' : m.compile_status === 'failed' ? 'No PDF yet. Fix the errors and compile again.' : m.compiled_at ? 'Loading the PDF…' : 'No PDF yet. Press Compile.')}
          </p>
        )}
      </div>
      {children}
    </section>
  )
}
