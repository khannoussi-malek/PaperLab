import { useCallback, useState, type MouseEvent } from 'react'
import type { Note, NoteKind } from '@/entities'
import type { ReaderTab } from '@/router/route'
import { useReferences } from '@/services/queries'
import type { tableMarks } from '@/features/datasets/pageMarks'
import { tableMarkerAt } from '@/features/datasets/pageMarks'
import { useHoverCard } from '@/features/reader/useHoverCard'
import { citationAt, clientPointToPdf, notesAt, rectContains } from '@/features/reader/hitTest'
import type { Citation } from '@/features/reader/citations'
import type { ContextMenuState } from '@/features/reader/ReaderContextMenu'
import { readAbstractSelection, readSelection, type NoteDraft } from '@/features/reader/selection'
import type { PdfRect } from '@/lib/coords'
import { scrollToElement } from '@/features/reader/readerScroll'
import type { PageHighlight } from '@/features/reader/pageHighlights'

/** The pointer in PDF points on the page under it, or null when it isn't over a page. */
function pointOnPage(event: MouseEvent, scale: number) {
  const element = (event.target as Element).closest<HTMLElement>('.pdf-page')
  if (!element) return null
  const point = clientPointToPdf({ x: event.clientX, y: event.clientY }, element.getBoundingClientRect(), scale)
  return { page: Number(element.dataset.page), point }
}

type Options = {
  paperId: string
  scale: number
  /** Remembers where a citation jump left from (the page's way back). */
  saveJump: (citation: Citation, viaKeyboard: boolean) => void
  noPdf: boolean
  tab: ReaderTab
  notes: Note[]
  citationsByPage: Map<number, Citation[]>
  highlightsByPage: Map<number, PageHighlight[]>
  tableMarksByPage: ReturnType<typeof tableMarks>
  draft: NoteDraft | null
  setDraft: (draft: NoteDraft | null) => void
  setWholePaperDraft: (draft: { kind: NoteKind | null } | null) => void
  setError: (message: string | null) => void
  blockedByTypedNote: () => boolean
  setActiveNoteId: (id: string | null) => void
  showTab: (next: ReaderTab) => void
  flashChunk: (page: number, rects: PdfRect[]) => void
  /** The capture drag: whether it is on, and how it ends on a mouse-up. */
  capturing: boolean
  endCaptureDrag: (event: MouseEvent) => void
}

/**
 * The reader's pointer side: citation and note hover cards, clicks on citations and table markers, selections
 * and the right-click menu, plus the way back from a citation jump.
 */
export function useReaderPointer(options: Options) {
  const { paperId, scale, saveJump, noPdf, tab, notes, citationsByPage, highlightsByPage, tableMarksByPage, draft, setDraft } = options
  const { setWholePaperDraft, setError, blockedByTypedNote, setActiveNoteId, showTab, flashChunk, capturing, endCaptureDrag } = options
  const references = useReferences(paperId, 'cites', citationsByPage.size > 0)
  const [editingNoteIds, setEditingNoteIds] = useState<string[]>([])
  // Ids of hover-card notes being edited; the card stays open while any is.
  const setNoteEditing = useCallback((noteId: string, editing: boolean) => {
    setEditingNoteIds((ids) => {
      if (editing === ids.includes(noteId)) return ids // unchanged: same array, no re-render
      return editing ? [...ids, noteId] : ids.filter((id) => id !== noteId)
    })
  }, [])
  const hoverCard = useHoverCard(editingNoteIds.length > 0)
  const [overCitation, setOverCitation] = useState(false)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)

  /** A citation's click, or Enter on its button: to its entry in the reference list, by the one scroll path (D147). */
  function jumpTo(citation: Citation, viaKeyboard: boolean) {
    // A note being edited keeps the card (D147): closing it here would unmount NoteCard and lose the unsaved edit.
    if (editingNoteIds.length === 0) hoverCard.close()
    saveJump(citation, viaKeyboard)
    flashChunk(citation.jump.page, citation.jump.rects)
  }

  /** A click on a citation jumps to its entry; one on a captured table's marker opens the Data tab. */
  function handlePageClick(event: MouseEvent) {
    if (capturing || readSelection(scale).kind !== 'none') return
    // A card's own clicks stay the card's, even over another citation; a citation button's click (Enter or Space)
    // has no pointer position and has already jumped.
    if ((event.target as Element).closest('.note-hover-card, .citation-card, .citation-link')) return
    const where = pointOnPage(event, scale)
    if (!where) return
    const citation = citationAt(citationsByPage.get(where.page) ?? [], where.point)
    if (citation) jumpTo(citation, false)
    else if (tableMarkerAt(tableMarksByPage.get(where.page) ?? [], where.point)) showTab('data')
  }

  function captureSelection(event: MouseEvent) {
    if (capturing) return endCaptureDrag(event)
    if (event.button !== 0) return // a right-click opens the menu instead
    const result = readSelection(scale)
    if (result.kind === 'invalid') setError(result.reason)
    const anchor = result.kind === 'anchor' ? result.anchor : noPdf ? readAbstractSelection() : null
    if (anchor) {
      if (blockedByTypedNote()) return
      setError(null)
      setDraft(anchor)
      setWholePaperDraft(null)
      if (tab !== 'notes') showTab('notes') // the composer lives on the Notes tab
    }
  }

  function editNote(note: Note) {
    const anchor = note.anchors.find((a) => a.paper_id === paperId)
    if (!anchor) return
    hoverCard.open({ kind: 'notes', page: anchor.page, noteIds: [note.id], editNoteId: note.id })
    // Same race as focusComposer: the closing menu's focus scope can steal focus back from the new textarea.
    // Scoped to this note: another note's hover or panel card can also have an "Edit note" textarea open.
    window.setTimeout(() =>
      document
        .querySelector<HTMLTextAreaElement>(`.note-hover-card [data-note-id="${note.id}"] textarea[aria-label="Edit note"]`)
        ?.focus(),
    )
  }

  /** The pointer left the card and what it shows: close soon, unless keyboard focus is on that citation or in its card. */
  function leaveCard() {
    const open = hoverCard.target
    if (open?.kind === 'citation' && document.activeElement?.closest(`[data-citation-id="${open.citationId}"]`)) return
    hoverCard.leave()
  }

  /**
   * Shows the citation or the notes under the pointer (a citation inside a highlight wins, D147); for notes, scrolls the
   * panel to the first one, only when that set changes.
   */
  function trackHover(event: MouseEvent) {
    if ((event.target as Element).closest('.note-hover-card, .citation-card')) {
      hoverCard.stay()
      return
    }
    const where = event.buttons === 0 ? pointOnPage(event, scale) : null // no preview while dragging a selection
    const citation = where ? citationAt(citationsByPage.get(where.page) ?? [], where.point) : null
    setOverCitation(citation !== null)
    if (where && citation) {
      hoverCard.show({ kind: 'citation', page: where.page, citationId: citation.id })
      return
    }
    const noteIds = where ? notesAt(highlightsByPage.get(where.page) ?? [], where.point) : []
    if (!where || noteIds.length === 0) {
      leaveCard()
      return
    }
    if (!hoverCard.show({ kind: 'notes', page: where.page, noteIds })) return
    setActiveNoteId(noteIds[0])
    scrollToElement(`article.note[data-note-id="${noteIds[0]}"]`, 'nearest')
  }

  /** Keyboard focus reached a citation's button (D147): its card opens, unless a note in the card is being edited. */
  function focusCitation(citation: Citation) {
    hoverCard.show({ kind: 'citation', page: citation.page, citationId: citation.id })
  }

  /** Focus left a citation and its card, or Escape: close its card, if it is the one open. */
  function closeCitationCard(citation: Citation) {
    const open = hoverCard.target
    if (open?.kind === 'citation' && open.citationId === citation.id) hoverCard.close()
  }

  /** Right-click on a highlight or the pending selection opens our menu; anywhere else keeps the browser's. */
  function openContextMenu(event: MouseEvent) {
    const where = pointOnPage(event, scale)
    if (!where) return
    const [noteId] = notesAt(highlightsByPage.get(where.page) ?? [], where.point)
    const note = notes.find((n) => n.id === noteId)
    // Once the composer opens it takes focus and the live selection is gone, so the draft is the usual target.
    // A selection that is still live (no composer yet) becomes the draft.
    const live = readSelection(scale)
    const pending = live.kind === 'anchor' ? live.anchor : draft
    const onPending =
      pending !== null && pending.page === where.page && pending.rects.some((rect) => rectContains(rect, where.point))
    if (!note && !(pending && onPending)) return

    event.preventDefault()
    hoverCard.close()
    if (note) {
      const quote = note.anchors.find((a) => a.paper_id === paperId)?.quoted_text ?? ''
      setMenu({ x: event.clientX, y: event.clientY, target: { kind: 'note', note, quote } })
    } else if (pending) {
      setDraft(pending)
      setMenu({ x: event.clientX, y: event.clientY, target: { kind: 'draft', quote: pending.quotedText, ...('figure' in pending && pending.figure ? { figure: true as const } : {}) } })
    }
  }

  return {
    references,
    hoverCard,
    setNoteEditing,
    overCitation,
    menu,
    setMenu,
    jumpTo,
    handlePageClick,
    captureSelection,
    editNote,
    leaveCard,
    trackHover,
    focusCitation,
    closeCitationCard,
    openContextMenu,
  }
}
