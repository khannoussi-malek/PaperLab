import { useEffect, useRef } from 'react'
import type { PDFDocumentProxy } from '@/features/reader/pdfjs'
import type { Note } from '@/entities'
import { useChunksOnPage } from '@/services/queries'
import { readerHref, type ReaderTab, type ReaderTarget } from '@/router/route'
import type { PdfRect } from '@/lib/coords'
import { scrollToPage } from '@/features/reader/readerScroll'

type Props = {
  paperId: string
  tab: ReaderTab
  /** A chunk to flash or a note to focus once, from the hash. */
  target: ReaderTarget
  doc: PDFDocumentProxy | null
  noPdf: boolean
  notesQuery: { data?: Note[] }
  flashChunk: (page: number, rects: PdfRect[]) => void
  focusNote: (note: Pick<Note, 'id'>) => void
}

/** The one-shot target from the hash: flashes its chunk, scrolls to its page, or focuses its note, then clears the hash. */
export function useReaderTarget({ paperId, tab, target, doc, noPdf, notesQuery, flashChunk, focusNote }: Props) {
  const shownTargetId = useRef<string | null>(null)
  const targetChunks = useChunksOnPage(paperId, target?.kind === 'chunk' ? target.page : null)

  // A one-shot target from the hash. Once the PDF and what the target needs have loaded, it goes
  // through the same path as a citation click or a note click, then leaves the hash so a reload doesn't repeat it.
  // replaceState fires no hashchange and adds no history entry, so Back still returns to where the link was.
  // A paper without a PDF has no page to show a passage on: any target but a note (a chat link's page 0) is dropped.
  useEffect(() => {
    if (noPdf && target?.kind !== 'note') {
      if (window.location.hash !== readerHref(paperId, tab)) window.history.replaceState(null, '', readerHref(paperId, tab))
      return
    }
    if ((!doc && !noPdf) || !target || shownTargetId.current === target.id) return
    if (target.kind === 'chunk') {
      if (!targetChunks.data) return
      const chunk = targetChunks.data.find((c) => c.id === target.id)
      if (chunk) flashChunk(chunk.page, chunk.bbox)
    } else if (target.kind === 'region') {
      flashChunk(target.page, target.rects)
    } else if (target.kind === 'page') {
      scrollToPage(target.page)
    } else {
      if (!notesQuery.data) return
      const note = notesQuery.data.find((n) => n.id === target.id)
      if (note) focusNote(note)
    }
    shownTargetId.current = target.id
    window.history.replaceState(null, '', readerHref(paperId, tab))
  })
}
