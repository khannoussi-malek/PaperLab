import { useEffect, useRef, useState } from 'react'
import type { Note } from '@/entities'
import type { ReaderTab } from '@/router/route'
import { scrollToElement } from '@/features/reader/readerScroll'

/** Which note is active, and how focusing a note scrolls to it on the page, the Notes tab or after a tab switch. */
export function useNoteFocus(paperId: string, tab: ReaderTab, notes: Note[], showTab: (next: ReaderTab) => void) {
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const promotedNoteId = useRef<string | null>(null)

  // Once the Notes tab is showing, bring a just-promoted note's card into view.
  useEffect(() => {
    if (tab !== 'notes' || !promotedNoteId.current) return
    scrollToElement(`article.note[data-note-id="${promotedNoteId.current}"]`, 'nearest')
    promotedNoteId.current = null
  }, [tab])

  function focusNote(note: Pick<Note, 'id'>) {
    setActiveNoteId(note.id)
    const highlighted = notes.some((n) => n.id === note.id && n.anchors.some((a) => a.paper_id === paperId))
    if (highlighted) return scrollToElement(`.highlight[data-note-id="${note.id}"]`, 'center')
    // A note on the whole paper has no highlight: its card in the Notes tab is where it is.
    if (tab === 'notes') return scrollToElement(`article.note[data-note-id="${note.id}"]`, 'nearest')
    promotedNoteId.current = note.id // the effect on `tab` scrolls to it once the Notes tab shows
    showTab('notes')
  }

  function showPromotedNote(note: Note) {
    setActiveNoteId(note.id)
    promotedNoteId.current = note.id
    showTab('notes')
  }

  return { activeNoteId, setActiveNoteId, focusNote, showPromotedNote }
}
