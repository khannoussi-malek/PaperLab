import { pdfRectToCss, type PdfRect } from '@/features/reader/coords'

/** The lens's fade on one page: the page's own white at 65% over each chunk outside the lens (spec §5). */
export function LensFade({ rects, scale }: { rects: PdfRect[]; scale: number }) {
  return rects.map((rect, i) => (
    <div key={i} className="lens-fade absolute bg-white/65" style={pdfRectToCss(rect, scale)} />
  ))
}
