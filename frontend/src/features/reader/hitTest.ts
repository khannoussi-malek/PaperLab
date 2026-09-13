import type { PdfRect } from './coords'

/** One drawn highlight rect; `noteId` is null for the unsaved draft. */
export type NoteRect = { noteId: string | null; rect: PdfRect }

export const rectContains = ([x0, y0, x1, y1]: PdfRect, [x, y]: [number, number]): boolean =>
  x >= x0 && x <= x1 && y >= y0 && y <= y1

/**
 * Highlights sit under the text layer with pointer-events off (so selection keeps working),
 * so hovering is resolved by position instead of by DOM events on the highlight itself.
 */
export function notesAt(highlights: NoteRect[], point: [number, number]): string[] {
  const hits = highlights
    .filter(({ noteId, rect }) => noteId !== null && rectContains(rect, point))
    .map(({ noteId }) => noteId as string)
  return [...new Set(hits)]
}

export function clientPointToPdf(
  point: { x: number; y: number },
  page: { left: number; top: number },
  scale: number,
): [number, number] {
  return [(point.x - page.left) / scale, (point.y - page.top) / scale]
}
