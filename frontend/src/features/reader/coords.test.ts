import { describe, expect, it } from 'vitest'
import { clientRectsToPdfRects, mergeLines, pdfRectToCss, type PdfRect } from './coords'

describe('pdfRectToCss', () => {
  it('scales PDF points to CSS pixels', () => {
    expect(pdfRectToCss([72, 400, 290, 410], 1.5)).toEqual({ left: 108, top: 600, width: 327, height: 15 })
  })
})

describe('mergeLines', () => {
  it('merges word boxes on one line but keeps separate lines and columns apart', () => {
    const words: PdfRect[] = [
      [100, 400, 130, 410], // line 1, second word (out of order)
      [72, 400, 98, 410], // line 1, first word
      [72, 412, 200, 422], // line 2
      [310, 400, 400, 410], // same height as line 1, but in the right-hand column
    ]
    expect(mergeLines(words)).toEqual([
      [72, 400, 130, 410],
      [310, 400, 400, 410],
      [72, 412, 200, 422],
    ])
  })
})

describe('clientRectsToPdfRects', () => {
  it('converts viewport pixels relative to the page into rounded PDF points', () => {
    const page = { left: 50, top: 1000, right: 943, bottom: 2263 }
    const selection = [
      { left: 158, top: 1600, right: 250, bottom: 1615 },
      { left: 251, top: 1600, right: 485, bottom: 1615 },
      { left: 60, top: 1010, right: 60, bottom: 1030 }, // zero-width caret box: ignored
    ]
    expect(clientRectsToPdfRects(selection, page, 1.5)).toEqual([[72, 400, 290, 410]])
  })

  it('round-trips with pdfRectToCss at any zoom', () => {
    const stored: PdfRect = [72.5, 409.25, 290.27, 420.13]
    for (const scale of [0.75, 1, 2.5]) {
      const css = pdfRectToCss(stored, scale)
      const client = { left: css.left, top: css.top, right: css.left + css.width, bottom: css.top + css.height }
      expect(clientRectsToPdfRects([client], { left: 0, top: 0, right: 0, bottom: 0 }, scale)).toEqual([stored])
    }
  })
})
