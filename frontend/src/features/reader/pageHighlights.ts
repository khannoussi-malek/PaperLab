import type { Note } from '@/entities'
import type { PdfRect } from '@/lib/coords'
import type { NoteDraft } from '@/features/reader/selection'

/** One drawn rect. `color` is its note's colour, or null for the pending selection (drawn with the draft token). */
export type PageHighlight = {
  key: string
  noteId: string | null
  color: string | null
  provenance?: Note['provenance']
  rect: PdfRect
  /** A figure note's rect: an outline in the note's colour, not a fill. */
  figure?: boolean
}

export function groupHighlights(notes: Note[], draft: NoteDraft | null, paperId: string) {
  const byPage = new Map<number, PageHighlight[]>()
  const add = (page: number, highlight: PageHighlight) =>
    byPage.set(page, [...(byPage.get(page) ?? []), highlight])

  for (const note of notes) {
    note.anchors.forEach((anchor, a) => {
      if (anchor.paper_id !== paperId) return
      anchor.bbox.forEach((rect, r) =>
        add(anchor.page, { key: `${note.id}-${a}-${r}`, noteId: note.id, color: note.color, provenance: note.provenance, rect, figure: note.kind === 'figure' }),
      )
    })
  }
  draft?.rects.forEach((rect, r) => add(draft.page, { key: `draft-${r}`, noteId: null, color: null, rect }))
  return byPage
}

const HOVER_CARD_GAP_PT = 4

/** The rects of these notes' highlights on one page. */
export const noteRects = (highlights: PageHighlight[], noteIds: string[]) =>
  highlights.filter((h) => h.noteId !== null && noteIds.includes(h.noteId)).map((h) => h.rect)

/** Places a hover card just below the lowest of `rects` (the hovered notes', or a citation's link), aligned with the leftmost. */
export function hoverCardPosition(rects: PdfRect[], scale: number) {
  const left = Math.min(...rects.map((r) => r[0]))
  const bottom = Math.max(...rects.map((r) => r[3]))
  return { left: left * scale, top: (bottom + HOVER_CARD_GAP_PT) * scale }
}
