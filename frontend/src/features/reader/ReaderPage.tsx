import { useCallback, useMemo, useState, type MouseEvent } from 'react'
import { api, type Note } from '@/api/client'
import { useNoteMutations, useNotes, usePaper } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { browserStorage, highlightFill, loadLastColor, saveLastColor } from '../notes/highlightColors'
import { NoteHoverCard } from '../notes/NoteHoverCard'
import { NotesPanel } from '../notes/NotesPanel'
import { pdfRectToCss, type PdfRect } from './coords'
import { clientPointToPdf, notesAt, rectContains } from './hitTest'
import { PdfPage } from './PdfPage'
import { ReaderContextMenu, type ContextMenuState } from './ReaderContextMenu'
import { ReaderToolbar } from './ReaderToolbar'
import { readSelection, type SelectionAnchor } from './selection'
import { useHoverCard } from './useHoverCard'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

/** One drawn rect. `color` is its note's colour, or null for the pending selection (drawn with the draft token). */
type PageHighlight = { key: string; noteId: string | null; color: string | null; rect: PdfRect }

function groupHighlights(notes: Note[], draft: SelectionAnchor | null, paperId: string) {
  const byPage = new Map<number, PageHighlight[]>()
  const add = (page: number, highlight: PageHighlight) =>
    byPage.set(page, [...(byPage.get(page) ?? []), highlight])

  for (const note of notes) {
    note.anchors.forEach((anchor, a) => {
      if (anchor.paper_id !== paperId) return
      anchor.bbox.forEach((rect, r) =>
        add(anchor.page, { key: `${note.id}-${a}-${r}`, noteId: note.id, color: note.color, rect }),
      )
    })
  }
  draft?.rects.forEach((rect, r) => add(draft.page, { key: `draft-${r}`, noteId: null, color: null, rect }))
  return byPage
}

const HOVER_CARD_GAP_PT = 4

/** Places the hover card just below the lowest rect of the hovered notes, aligned with the leftmost. */
function hoverCardPosition(highlights: PageHighlight[], noteIds: string[], scale: number) {
  const rects = highlights.filter((h) => h.noteId !== null && noteIds.includes(h.noteId)).map((h) => h.rect)
  const left = Math.min(...rects.map((r) => r[0]))
  const bottom = Math.max(...rects.map((r) => r[3]))
  return { left: left * scale, top: (bottom + HOVER_CARD_GAP_PT) * scale }
}

/** The pointer in PDF points on the page under it, or null when it isn't over a page. */
function pointOnPage(event: MouseEvent, scale: number) {
  const element = (event.target as Element).closest<HTMLElement>('.pdf-page')
  if (!element) return null
  const point = clientPointToPdf({ x: event.clientX, y: event.clientY }, element.getBoundingClientRect(), scale)
  return { page: Number(element.dataset.page), point }
}

export function ReaderPage({ paperId }: { paperId: string }) {
  const { doc, error: pdfError } = usePdfDocument(api.paperFileUrl(paperId))
  const paper = usePaper(paperId)
  const notesQuery = useNotes(paperId)
  const mutations = useNoteMutations(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const [draft, setDraft] = useState<SelectionAnchor | null>(null)
  const [draftColor, setDraftColor] = useState(() => loadLastColor(browserStorage()))
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  // Ids of hover-card notes being edited; the card stays open while any is.
  const [editingNoteIds, setEditingNoteIds] = useState<string[]>([])
  const setNoteEditing = useCallback((noteId: string, editing: boolean) => {
    setEditingNoteIds((ids) => {
      if (editing === ids.includes(noteId)) return ids // unchanged: same array, no re-render
      return editing ? [...ids, noteId] : ids.filter((id) => id !== noteId)
    })
  }, [])
  const hoverCard = useHoverCard(editingNoteIds.length > 0)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scale = ZOOM_STEPS[zoomIndex]
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])

  const highlightsByPage = useMemo(() => groupHighlights(notes, draft, paperId), [notes, draft, paperId])

  /** Runs a mutation; failures show in the alert instead of throwing. */
  async function attempt(action: () => Promise<unknown>): Promise<boolean> {
    try {
      await action()
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  function captureSelection(event: MouseEvent) {
    if (event.button !== 0) return // a right-click opens the menu instead
    const result = readSelection(scale)
    if (result.kind === 'invalid') setError(result.reason)
    if (result.kind === 'anchor') {
      setError(null)
      setDraft(result.anchor)
    }
  }

  async function saveDraft(body: string, color: string = draftColor): Promise<boolean> {
    if (!draft) return false
    const anchor = { paper_id: paperId, page: draft.page, bbox: draft.rects, quoted_text: draft.quotedText }
    const saved = await attempt(() => mutations.create.mutateAsync({ body, color, anchor }))
    if (saved) {
      saveLastColor(browserStorage(), color)
      setDraft(null)
      window.getSelection()?.removeAllRanges()
    }
    return saved
  }

  async function highlightDraft(color: string) {
    setDraftColor(color)
    await saveDraft('', color)
  }

  const updateNoteBody = (note: Note, body: string) =>
    attempt(() => mutations.update.mutateAsync({ id: note.id, body }))

  const recolorNote = (note: Note, color: string) =>
    attempt(() => mutations.update.mutateAsync({ id: note.id, color }))

  async function deleteNote(note: Note) {
    if (!window.confirm('Delete this note?')) return
    await attempt(() => mutations.remove.mutateAsync(note.id))
  }

  function focusNote(note: Note) {
    setActiveNoteId(note.id)
    document
      .querySelector(`.highlight[data-note-id="${note.id}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function editNote(note: Note) {
    const anchor = note.anchors.find((a) => a.paper_id === paperId)
    if (!anchor) return
    hoverCard.open({ page: anchor.page, noteIds: [note.id], editNoteId: note.id })
    // Same race as focusComposer: the closing menu's focus scope can steal focus back from the new textarea.
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Edit note"]')?.focus())
  }

  function focusComposer() {
    // After the menu has finished closing, or its focus handling takes focus straight back.
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Note"]')?.focus())
  }

  /** Shows the notes under the pointer and scrolls the panel to the first, only when that set changes. */
  function trackHover(event: MouseEvent) {
    if ((event.target as Element).closest('.note-hover-card')) {
      hoverCard.stay()
      return
    }
    const where = event.buttons === 0 ? pointOnPage(event, scale) : null // no preview while dragging a selection
    const noteIds = where ? notesAt(highlightsByPage.get(where.page) ?? [], where.point) : []
    if (!where || noteIds.length === 0) {
      hoverCard.leave()
      return
    }
    if (!hoverCard.show({ page: where.page, noteIds })) return
    setActiveNoteId(noteIds[0])
    document
      .querySelector(`article.note[data-note-id="${noteIds[0]}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
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
      setMenu({ x: event.clientX, y: event.clientY, target: { kind: 'draft', quote: pending.quotedText } })
    }
  }

  const hover = hoverCard.target
  const hoveredNotes = hover ? notes.filter((note) => hover.noteIds.includes(note.id)) : []

  const shownError = error ?? paper.error?.message ?? notesQuery.error?.message ?? pdfError
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)_360px] grid-rows-[auto_minmax(0,1fr)]">
      <ReaderToolbar title={paper.data?.title} zoomIndex={zoomIndex} onZoomChange={setZoomIndex} />

      {shownError && (
        <Alert
          variant="destructive"
          className={cn('fixed bottom-4 left-4 z-10 w-auto max-w-md cursor-pointer border-glass-border shadow-lg', glass)}
          onClick={() => setError(null)}
        >
          <AlertDescription>{shownError}</AlertDescription>
        </Alert>
      )}

      <section
        className="overflow-auto p-4"
        onMouseUp={captureSelection}
        onMouseMove={trackHover}
        onMouseLeave={hoverCard.leave}
        onContextMenu={openContextMenu}
      >
        {doc &&
          Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale}>
              {(highlightsByPage.get(pageNumber) ?? []).map((h) => (
                <div
                  key={h.key}
                  data-note-id={h.noteId ?? undefined}
                  className={cn(
                    'highlight absolute rounded-xs mix-blend-multiply',
                    h.noteId === null && 'draft bg-highlight-draft',
                    // An outline, not a colour swap: any colour can be the note's own.
                    h.noteId !== null && h.noteId === activeNoteId && 'active outline-2 outline-offset-1 outline-primary',
                  )}
                  style={{ ...pdfRectToCss(h.rect, scale), backgroundColor: h.color ? highlightFill(h.color) : undefined }}
                />
              ))}
              {hover?.page === pageNumber && hoveredNotes.length > 0 && (
                <NoteHoverCard
                  notes={hoveredNotes}
                  paperId={paperId}
                  style={hoverCardPosition(highlightsByPage.get(pageNumber) ?? [], hover.noteIds, scale)}
                  editNoteId={hover.editNoteId}
                  onPointerEnter={hoverCard.stay}
                  onPointerLeave={hoverCard.leave}
                  onEditingChange={setNoteEditing}
                  onUpdate={updateNoteBody}
                  onColorChange={recolorNote}
                  onDelete={deleteNote}
                />
              )}
            </PdfPage>
          ))}
      </section>

      <NotesPanel
        paperId={paperId}
        notes={notes}
        draft={draft}
        draftColor={draftColor}
        activeNoteId={activeNoteId}
        onDraftColorChange={setDraftColor}
        onSaveDraft={saveDraft}
        onCancelDraft={() => setDraft(null)}
        onSelectNote={focusNote}
        onUpdateNote={updateNoteBody}
        onColorNote={recolorNote}
        onDeleteNote={deleteNote}
      />

      <ReaderContextMenu
        menu={menu}
        onClose={() => setMenu(null)}
        onColorNote={(note, color) => void recolorNote(note, color)}
        onEditNote={editNote}
        onDeleteNote={(note) => void deleteNote(note)}
        onHighlightDraft={(color) => void highlightDraft(color)}
        onAddNote={focusComposer}
        onCancelDraft={() => setDraft(null)}
      />
    </div>
  )
}
