import { useCallback, useEffect, useRef, useState } from 'react'
import type { Paper } from '@/api/client'
import { browserStorage } from '@/features/notes/highlightColors'
import type { DeskLayout } from './layout'
import type { DeskTab } from './PdfTabs'

const PDF_KEY = 'paperlab-triage-pdf'

function storedPdfOn(): boolean {
  try {
    return browserStorage()?.getItem(PDF_KEY) !== '0'
  } catch {
    return true
  }
}

/** Where the PDF is, for each layout: the column (wide), the tab (tabs) or the sheet (single), and the page it was left on. */
export function useDeskPdf(layout: DeskLayout, top: Paper | null | undefined) {
  const [pdfOn, setPdfOn] = useState(storedPdfOn)
  const [tab, setTab] = useState<DeskTab>('paper')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [jump, setJump] = useState<{ paperId: string; page: number; n: number } | null>(null)
  const showRequested = useRef(false)
  const delivered = useRef(0) // a Show in PDF jump is applied once; later mounts restore the remembered page instead
  const pages = useRef(new Map<string, number>())
  const topId = top?.id
  const hasPdf = Boolean(top?.has_pdf)
  const column = layout === 'wide' && pdfOn && hasPdf
  const tabsOn = layout === 'tabs' && hasPdf
  const pdfTab = tabsOn && tab === 'pdf'
  const sheetShown = layout === 'single' && hasPdf && sheetOpen
  const mounted = column || tabsOn || sheetShown // tab panels both stay mounted: the PDF keeps its page
  const shown = column || pdfTab || sheetShown

  const toggle = () => {
    if (layout === 'tabs') return hasPdf && setTab(tab === 'pdf' ? 'paper' : 'pdf')
    if (layout === 'single') return hasPdf && setSheetOpen(!sheetOpen)
    const next = !pdfOn
    setPdfOn(next)
    try {
      browserStorage()?.setItem(PDF_KEY, next ? '1' : '0')
    } catch {
      // ponytail: an unwritable store only means the choice is forgotten on reload
    }
  }
  const showAt = (page: number) => {
    if (!topId) return
    showRequested.current = true
    if (layout === 'wide') setPdfOn(true)
    else if (layout === 'tabs') setTab('pdf')
    else setSheetOpen(true)
    setJump((j) => ({ paperId: topId, page, n: (j?.n ?? 0) + 1 }))
  }
  // eslint-disable-next-line react/refs -- read only to pass the jump on once; it never drives a re-render
  const target = jump && jump.paperId === topId && jump.n !== delivered.current ? jump : null
  useEffect(() => { if (target && mounted) delivered.current = target.n })
  /** True once, when a Show in PDF has made the PDF visible: the caller counts it as an interaction. */
  const takeShowRequest = () => {
    if (!showRequested.current || !shown) return false
    showRequested.current = false
    return true
  }
  const remember = useCallback((paperId: string, page: number) => { pages.current.set(paperId, page) }, [])
  return {
    hasPdf, column, tabsOn, pdfTab, sheetShown, mounted, shown, tab, setTab, sheetOpen, setSheetOpen,
    toggle, showAt, target, takeShowRequest, remember, pageOf: (id: string) => pages.current.get(id),
  }
}
