/**
 * Three coordinate systems meet in the reader:
 * - PDF points, top-left origin: what the backend stores (PyMuPDF) and the only thing we persist.
 * - CSS pixels inside a rendered page: PDF points × scale.
 * - Viewport pixels from the DOM (getClientRects): CSS pixels offset by the page's position.
 * Convert at render time; never store anything but PDF points.
 */

export type PdfRect = [x0: number, y0: number, x1: number, y1: number]
export type CssBox = { left: number; top: number; width: number; height: number }
export type ClientRectLike = { left: number; top: number; right: number; bottom: number }

// Word boxes closer than this (in points) on the same line merge; column gaps are wider.
const SAME_LINE_GAP_PT = 6

export function pdfRectToCss([x0, y0, x1, y1]: PdfRect, scale: number): CssBox {
  return { left: x0 * scale, top: y0 * scale, width: (x1 - x0) * scale, height: (y1 - y0) * scale }
}

function onSameLine(a: PdfRect, b: PdfRect): boolean {
  const verticalOverlap = Math.min(a[3], b[3]) - Math.max(a[1], b[1])
  const smallerHeight = Math.min(a[3] - a[1], b[3] - b[1])
  const horizontalGap = Math.max(a[0], b[0]) - Math.min(a[2], b[2])
  return verticalOverlap >= smallerHeight / 2 && horizontalGap <= SAME_LINE_GAP_PT
}

export function mergeLines(rects: PdfRect[]): PdfRect[] {
  const sorted = [...rects].sort((a, b) => a[1] - b[1] || a[0] - b[0])
  return sorted.reduce<PdfRect[]>((lines, rect) => {
    const index = lines.findIndex((line) => onSameLine(line, rect))
    if (index === -1) return [...lines, rect]
    const line = lines[index]
    const merged: PdfRect = [
      Math.min(line[0], rect[0]),
      Math.min(line[1], rect[1]),
      Math.max(line[2], rect[2]),
      Math.max(line[3], rect[3]),
    ]
    return lines.map((existing, i) => (i === index ? merged : existing))
  }, [])
}

export function clientRectsToPdfRects(rects: ClientRectLike[], page: ClientRectLike, scale: number): PdfRect[] {
  const round = (value: number) => Math.round(value * 100) / 100
  const inPoints = rects
    .filter((r) => r.right - r.left > 0.5 && r.bottom - r.top > 0.5)
    .map((r): PdfRect => [
      (r.left - page.left) / scale,
      (r.top - page.top) / scale,
      (r.right - page.left) / scale,
      (r.bottom - page.top) / scale,
    ])
  return mergeLines(inPoints).map(([x0, y0, x1, y1]): PdfRect => [round(x0), round(y0), round(x1), round(y1)])
}
