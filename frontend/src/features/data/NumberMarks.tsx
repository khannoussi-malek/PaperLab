import { pdfRectToCss } from '../reader/coords'
import type { NumberMark } from './pageMarks'

type Props = { marks: NumberMark[]; scale: number }

/** A page's captured-number underlines: a dashed bottom border under each anchored rect. */
export function NumberMarks({ marks, scale }: Props) {
  return marks.flatMap((mark) =>
    mark.rects.map((rect, r) => (
      <div
        key={`${mark.rowId}-${r}`}
        className="number-mark absolute border-b-2 border-dashed border-foreground/60"
        style={pdfRectToCss(rect, scale)}
      />
    )),
  )
}
