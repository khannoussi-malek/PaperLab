import { pdfRectToCss } from '../reader/coords'
import type { NumberMark } from './pageMarks'

type Props = { marks: NumberMark[]; scale: number }

/** A page's captured-number underlines: a dashed bottom border under each anchored rect. */
export function NumberMarks({ marks, scale }: Props) {
  return marks.flatMap((mark) =>
    mark.rects.map((rect, r) => (
      <div
        key={`${mark.rowId}-${r}`}
        // Fixed dark colour, not the `foreground` token: the mark sits on the PDF page, which stays white in both themes.
        className="number-mark absolute border-b-2 border-dashed border-slate-900/60"
        style={pdfRectToCss(rect, scale)}
      />
    )),
  )
}
