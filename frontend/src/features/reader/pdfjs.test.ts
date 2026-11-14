// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'

const pdfjsGetDocument = vi.fn()
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, PDFWorker: class {}, getDocument: pdfjsGetDocument }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'worker.js' }))
vi.mock('pdfjs-dist/web/pdf_viewer.mjs', () => ({ TextLayerBuilder: class {} }))

describe('getDocument', () => {
  it('points PDF.js at its image decoders, so scanned (CCITT/JBIG2/JPEG 2000) pages are not blank', async () => {
    const { getDocument } = await import('./pdfjs')
    getDocument({ url: '/api/papers/p/file' })
    const options = pdfjsGetDocument.mock.calls[0][0]
    expect(options.url).toBe('/api/papers/p/file')
    // An absolute folder URL: the worker fetches `${wasmUrl}jbig2.wasm` itself, from its own location.
    expect(options.wasmUrl).toBe(`${location.origin}/pdfjs-wasm/`)
  })
})
