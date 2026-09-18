// The single entry point to PDF.js. Import order matters: pdf_viewer.mjs reads
// globalThis.pdfjsLib, which only exists once pdfjs-dist has been evaluated.
import { GlobalWorkerOptions, PDFWorker, getDocument } from 'pdfjs-dist'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import 'pdfjs-dist/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = workerSrc

// One worker for every document, started as soon as PDF.js loads, so it is ready before the first paper opens. Left to
// itself, getDocument starts a worker per document and its destroy() ends it: ~250 ms on every open and every library
// preview. A loading task given `worker` never destroys it.
export const pdfWorker = new PDFWorker()

export { getDocument, TextLayerBuilder }
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
