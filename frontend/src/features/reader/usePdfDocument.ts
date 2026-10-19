import { useEffect, useState } from 'react'
import { getDocument, pdfWorker, type PDFDocumentProxy } from './pdfjs'

type PdfState = { doc: PDFDocumentProxy | null; error: string | null }

/** The PDF at `url`; with null (a paper without a PDF, or not known yet) it asks for nothing and stays empty. */
export function usePdfDocument(url: string | null): PdfState {
  const [state, setState] = useState<PdfState>({ doc: null, error: null })

  useEffect(() => {
    if (url === null) return
    let active = true
    const task = getDocument({ url, worker: pdfWorker })
    task.promise.then(
      (doc) => active && setState({ doc, error: null }),
      (error: Error) => active && setState({ doc: null, error: `Could not open PDF: ${error.message}` }),
    )
    return () => {
      active = false
      void task.destroy()
    }
  }, [url])

  return state
}
