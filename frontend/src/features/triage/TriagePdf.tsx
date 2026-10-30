import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { ChevronLeft, ChevronRight, Minus, Plus, Scan } from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { PdfPage } from '../reader/PdfPage'
import { ZOOM_STEPS } from '../reader/zoom'
import { useCachedPdf } from './pdfCache'
import { usePdfInteraction } from './usePdfInteraction'

const PAGE_WIDTH_PT = 612
const GUTTERS_PX = 24
const FIT_INDEX = 1 // ZOOM_STEPS[1] is 1x: the page fills the column
const LAST_ZOOM = ZOOM_STEPS.length - 1

type Jump = { page: number; n: number }
type Props = {
  paperId: string
  /** The column is shown: nothing is fetched or rendered otherwise. */
  active: boolean
  /** A page to bring to the top (Show in PDF); a new `n` re-places it. */
  target: Jump | null
  onInteract: () => void
  onPage?: (page: number, total: number) => void
}

function Column({ paperId, target, onInteract, onPage }: Omit<Props, 'active'>) {
  const { doc, error } = useCachedPdf(api.paperFileUrl(paperId))
  const total = doc?.numPages ?? 0
  const [zoom, setZoom] = useState(FIT_INDEX)
  const [page, setPage] = useState(1)
  const [jump, setJump] = useState<Jump | null>(null)
  const [width, setWidth] = useState(0)
  const [pageWidth, setPageWidth] = useState(PAGE_WIDTH_PT)
  const scroller = useRef<HTMLDivElement>(null)
  const stack = useRef<HTMLDivElement>(null)
  const pending = useRef(false) // a jump not yet settled: pages measuring move it, the reader's own scrolling cancels it
  const seq = useRef(0)
  usePdfInteraction(scroller, onInteract)

  const fit = width > 0 ? Math.max(0.4, (width - GUTTERS_PX) / pageWidth) : 1
  const scale = fit * ZOOM_STEPS[zoom]

  useEffect(() => {
    const box = scroller.current
    if (!box) return
    setWidth(box.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setWidth(box.clientWidth)) // a resize reflows; it is never an interaction
    ro.observe(box)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    void doc?.getPage(1).then((p) => setPageWidth(p.getViewport({ scale: 1 }).width), () => {})
  }, [doc])

  const place = useCallback(() => {
    const box = scroller.current
    const el = box?.querySelector<HTMLElement>(`[data-page="${jump?.page}"]`)
    if (!box || !el) return
    box.scrollTop = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop
  }, [jump])
  useEffect(() => { pending.current = jump !== null; place() }, [jump, doc]) // eslint-disable-line react-hooks/exhaustive-deps -- placed again by the observer, not by a resize
  useEffect(() => {
    const el = stack.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => { if (pending.current) place() }) // pages learn their size after mounting
    ro.observe(el)
    return () => ro.disconnect()
  }, [place, doc])

  const go = useCallback((n: number) => setJump({ page: n, n: ++seq.current }), [])
  const newTarget = useRef<Jump | null>(null)
  useEffect(() => {
    if (!target || target === newTarget.current) return
    newTarget.current = target
    setPage(target.page)
    go(target.page)
    onInteract() // the reader asked for that page
  }, [target, go, onInteract])
  useEffect(() => { if (total > 0) onPage?.(page, total) }, [page, total]) // eslint-disable-line react-hooks/exhaustive-deps

  const turn = (to: number) => {
    if (to < 1 || to > total || to === page) return
    setPage(to)
    go(to)
    onInteract()
  }
  const zoomTo = (z: number) => {
    const next = Math.min(LAST_ZOOM, Math.max(0, z))
    if (next === zoom) return
    setZoom(next)
    go(page) // keep the page in view as it grows; the scroll it causes has no input before it
    onInteract()
  }
  const measure = () => {
    const box = scroller.current
    if (!box || pending.current) return
    const line = box.getBoundingClientRect().top + box.clientHeight / 4 // ponytail: the page crossing the top quarter is "current"
    let at = 1
    box.querySelectorAll<HTMLElement>('[data-page]').forEach((p) => { if (p.getBoundingClientRect().top <= line) at = Number(p.dataset.page) })
    setPage(at)
  }
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey) return
    const handled = ['[', ']', 'PageUp', 'PageDown', '+', '=', '-', '0'].includes(e.key)
    if (e.key === '[' || e.key === 'PageUp') turn(page - 1)
    else if (e.key === ']' || e.key === 'PageDown') turn(page + 1)
    else if (e.key === '+' || e.key === '=') zoomTo(zoom + 1)
    else if (e.key === '-') zoomTo(zoom - 1)
    else if (e.key === '0') zoomTo(FIT_INDEX)
    if (handled) e.preventDefault()
  }

  return (
    <>
      <div className="flex items-center gap-1 border-b border-border px-2 py-1 text-sm">
        <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => turn(page - 1)}><ChevronLeft /></Button>
        <span className="min-w-24 text-center tabular-nums">{total > 0 ? `Page ${page} of ${total}` : 'PDF'}</span>
        <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= total} onClick={() => turn(page + 1)}><ChevronRight /></Button>
        <span className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" aria-label="Zoom out" disabled={zoom === 0} onClick={() => zoomTo(zoom - 1)}><Minus /></Button>
          <Button variant="ghost" size="icon-sm" aria-label="Fit width" onClick={() => zoomTo(FIT_INDEX)}><Scan /></Button>
          <Button variant="ghost" size="icon-sm" aria-label="Zoom in" disabled={zoom === LAST_ZOOM} onClick={() => zoomTo(zoom + 1)}><Plus /></Button>
        </span>
      </div>
      <div
        ref={scroller}
        tabIndex={0}
        aria-label="PDF pages"
        onKeyDown={keys}
        onScroll={measure}
        onWheel={() => { pending.current = false }}
        onPointerDown={() => { pending.current = false }}
        className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {doc ? (
          <div ref={stack}>
            {Array.from({ length: total }, (_, i) => i + 1).map((n) => <PdfPage key={n} doc={doc} pageNumber={n} scale={scale} />)}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{error ? "Couldn't open the PDF. The abstract is still here." : 'Loading the PDF…'}</p>
        )}
      </div>
    </>
  )
}

/** The paper's PDF beside the card. Deciding never waits on it; only what the reader does here counts as opening it. */
export function TriagePdf({ active, ...rest }: Props) {
  if (!active) return null
  return (
    <section aria-label="PDF" data-triage-region data-triage-pdf tabIndex={-1} className="glass flex h-[78vh] min-h-96 flex-col overflow-hidden rounded-2xl border border-border outline-none">
      <Column {...rest} />
    </section>
  )
}
