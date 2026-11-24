import { useEffect, useState } from 'react'
import type { PDFDocumentProxy } from '@/features/reader/pdfjs'
import type { PdfRect } from '@/lib/coords'
import { scrollToElement, scrollToPage } from '@/features/reader/readerScroll'

const FLASH_MS = 1500

/** A cited chunk being shown; `id` restarts the flash when the same citation is clicked again. */
export type Flash = { id: number; page: number; rects: PdfRect[] }

/** The flash on a cited chunk, and the function that starts one. */
export function useFlash(doc: PDFDocumentProxy | null) {
  const [flash, setFlash] = useState<Flash | null>(null)

  // Rendering the flash first gives the scroll a target, even on a page whose canvas hasn't rendered yet.
  // A flash asked for before the PDF has loaded (Show in paper clicked straight after opening) waits for `doc`,
  // since until then no page exists to draw it on or scroll to.
  useEffect(() => {
    if (!flash || !doc) return
    // A passage with no boxes (a citation whose chunk a re-ingest replaced) still takes the reader to its page.
    if (flash.rects.length === 0) scrollToPage(flash.page)
    else scrollToElement('.chunk-flash', 'center')
    const timer = window.setTimeout(() => setFlash(null), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [flash, doc])

  const flashChunk = (page: number, rects: PdfRect[]) => setFlash({ id: Date.now(), page, rects })
  return { flash, flashChunk }
}
