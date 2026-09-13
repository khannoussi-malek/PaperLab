// The single entry point to PDF.js. Import order matters: pdf_viewer.mjs reads
// globalThis.pdfjsLib, which only exists once pdfjs-dist has been evaluated.
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import 'pdfjs-dist/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = workerSrc

export { getDocument, TextLayerBuilder }
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
