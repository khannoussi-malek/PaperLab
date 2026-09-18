import { useEffect, useState } from 'react'
import { citationsByPage, readCitations, type Citation } from './citations'
import type { PDFDocumentProxy } from './pdfjs'

/** The pass waits for the browser to be idle, at most this long (D149)... */
const IDLE_TIMEOUT_MS = 1000
/** ...or, where `requestIdleCallback` is missing (Safari), this long. */
const NO_IDLE_DELAY_MS = 300

const NONE = new Map<number, Citation[]>()

/** Runs `task` when the browser is next idle; returns the cancel. */
function whenIdle(task: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const handle = window.requestIdleCallback(task, { timeout: IDLE_TIMEOUT_MS })
    return () => window.cancelIdleCallback(handle)
  }
  const timer = window.setTimeout(task, NO_IDLE_DELAY_MS)
  return () => window.clearTimeout(timer)
}

/**
 * The document's citations by page, empty until the pass is done (D143, D149). The pass starts once the browser is
 * idle after the paper opens, so it never competes with page 1's first paint for the one PDF.js worker. Nothing is
 * stored: the result belongs to this `doc`, and is dropped when it changes or the reader unmounts.
 */
export function useCitations(doc: PDFDocumentProxy | null): Map<number, Citation[]> {
  const [read, setRead] = useState<{ doc: PDFDocumentProxy; byPage: Map<number, Citation[]> } | null>(null)

  useEffect(() => {
    if (!doc) return
    let active = true
    const cancel = whenIdle(() => {
      readCitations(doc).then(
        (citations) => active && setRead({ doc, byPage: citationsByPage(citations) }),
        // A failed pass leaves the reader without citations, and otherwise working. After unmount the destroyed
        // document fails whatever was still being read, which is not worth a log.
        (error: unknown) => active && console.error('citations', error),
      )
    })
    return () => {
      active = false
      cancel()
    }
  }, [doc])

  return read?.doc === doc ? read.byPage : NONE
}
