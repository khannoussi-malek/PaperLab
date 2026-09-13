import type { PdfRect } from './coords'

/** One drawn highlight rect; `noteId` is null for the unsaved draft. */
export type NoteRect = { noteId: string | null; rect: PdfRect }

/**
 * Highlights sit under the text layer with pointer-events off (so selection keeps working),
 * so hovering is resolved by position instead of by DOM events on the highlight itself.
 */
export function notesAt(highlights: NoteRect[], [x, y]: [number, number]): string[] {
  const hits = highlights
    .filter(({ noteId, rect: [x0, y0, x1, y1] }) => noteId !== null && x >= x0 && x <= x1 && y >= y0 && y <= y1)
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
