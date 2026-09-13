import { useEffect, useState } from 'react'
import { getDocument, type PDFDocumentProxy } from './pdfjs'

type PdfState = { doc: PDFDocumentProxy | null; error: string | null }

export function usePdfDocument(url: string): PdfState {
  const [state, setState] = useState<PdfState>({ doc: null, error: null })

  useEffect(() => {
    let active = true
    const task = getDocument({ url })
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
