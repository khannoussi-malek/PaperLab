// The single entry point to PDF.js. Import order matters: pdf_viewer.mjs reads
// globalThis.pdfjsLib, which only exists once pdfjs-dist has been evaluated.
import { GlobalWorkerOptions, PDFWorker, getDocument as pdfjsGetDocument } from 'pdfjs-dist'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import 'pdfjs-dist/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = workerSrc

// One worker for every document, started as soon as PDF.js loads, so it is ready before the first paper opens. Left to
// itself, getDocument starts a worker per document and its destroy() ends it: ~250 ms on every open and every library
// preview. A loading task given `worker` never destroys it.
// ponytail: one worker means a document stuck in a long decode delays the next one, and a PDF that hangs PDF.js hangs
// every PDF until a reload (before, destroy() killed that document's own worker). Replace the worker when a destroyed
// task hasn't settled within a second or two if that ever shows up.
export const pdfWorker = new PDFWorker()

// PDF.js decodes CCITT fax, JBIG2 and JPEG 2000 images with WebAssembly it fetches from `wasmUrl` (vite.config.ts
// serves its wasm/ folder there). Without it every page of a scanned paper renders blank, with only the text layer.
// Absolute, because the worker fetches `${wasmUrl}jbig2.wasm` relative to its own location.
const wasmUrl = new URL(`${import.meta.env.BASE_URL}pdfjs-wasm/`, location.origin).href

export const getDocument = (src: Exclude<Parameters<typeof pdfjsGetDocument>[0], string | URL | ArrayBuffer | Uint8Array>) =>
  pdfjsGetDocument({ wasmUrl, ...src })

export { TextLayerBuilder }
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
