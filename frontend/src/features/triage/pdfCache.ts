import { useEffect, useState } from 'react'
import { getDocument, pdfWorker, type PDFDocumentProxy } from '../reader/pdfjs'

type Entry = { task: ReturnType<typeof getDocument>; refs: number; doc: PDFDocumentProxy | null; error: string | null }

const entries = new Map<string, Entry>()
let retained = new Set<string>()

function open(url: string): Entry {
  let e = entries.get(url)
  if (!e) {
    const task = getDocument({ url, worker: pdfWorker })
    const made: Entry = { task, refs: 0, doc: null, error: null }
    task.promise.then(
      (doc) => { made.doc = doc },
      (err: Error) => { made.error = `Could not open PDF: ${err.message}` },
    )
    entries.set(url, made)
    e = made
  }
  return e
}

function dropIfIdle(url: string) {
  const e = entries.get(url)
  if (!e || e.refs > 0 || retained.has(url)) return
  entries.delete(url)
  void e.task.destroy() // a destroyed document is out of the map first, so nobody is handed it again
}

/** Start fetching a document nobody has mounted yet. */
export function prefetchPdf(url: string) { open(url) }
export function acquirePdf(url: string): Entry {
  if (entries.get(url)?.error && entries.get(url)?.refs === 0) entries.delete(url) // a failed fetch is retried, not remembered
  const e = open(url); e.refs++; return e }
export function releasePdf(url: string) {
  const e = entries.get(url)
  if (e) { e.refs--; dropIfIdle(url) }
}

/** Keep exactly these documents warm: the rest are destroyed now, or when their last page lets go. */
export function retainOnly(urls: string[]) {
  retained = new Set(urls)
  for (const url of [...entries.keys()]) dropIfIdle(url)
}

type PdfState = { url: string | null; doc: PDFDocumentProxy | null; error: string | null }

/** The shared, reference-counted document at `url`; with null it asks for nothing. */
export function useCachedPdf(url: string | null): { doc: PDFDocumentProxy | null; error: string | null } {
  const [state, setState] = useState<PdfState>({ url: null, doc: null, error: null })
  useEffect(() => {
    if (url === null) return
    let active = true
    const e = acquirePdf(url)
    e.task.promise.then(
      (doc) => active && setState({ url, doc, error: null }),
      () => active && setState({ url, doc: null, error: e.error ?? 'Could not open PDF' }),
    )
    return () => { active = false; releasePdf(url) }
  }, [url])
  return state.url === url ? state : { doc: null, error: null }
}
