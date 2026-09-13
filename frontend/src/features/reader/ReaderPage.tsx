import { useMemo, useState, type MouseEvent } from 'react'
import { api, type Note } from '@/api/client'
import { useNoteMutations, useNotes, usePaper } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { NoteHoverCard } from '../notes/NoteHoverCard'
import { NotesPanel } from '../notes/NotesPanel'
import { pdfRectToCss, type PdfRect } from './coords'
import { clientPointToPdf, notesAt } from './hitTest'
import { PdfPage } from './PdfPage'
import { ReaderToolbar } from './ReaderToolbar'
import { readSelection, type SelectionAnchor } from './selection'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

type PageHighlight = { key: string; noteId: string | null; rect: PdfRect }

function groupHighlights(notes: Note[], draft: SelectionAnchor | null, paperId: string) {
  const byPage = new Map<number, PageHighlight[]>()
  const add = (page: number, highlight: PageHighlight) =>
    byPage.set(page, [...(byPage.get(page) ?? []), highlight])

  for (const note of notes) {
    note.anchors.forEach((anchor, a) => {
      if (anchor.paper_id !== paperId) return
      anchor.bbox.forEach((rect, r) => add(anchor.page, { key: `${note.id}-${a}-${r}`, noteId: note.id, rect }))
    })
  }
  draft?.rects.forEach((rect, r) => add(draft.page, { key: `draft-${r}`, noteId: null, rect }))
  return byPage
}

type Hover = { page: number; noteIds: string[] }

const HOVER_CARD_GAP_PT = 4

/** Places the hover card just below the lowest rect of the hovered notes, aligned with the leftmost. */
function hoverCardPosition(highlights: PageHighlight[], noteIds: string[], scale: number) {
  const rects = highlights.filter((h) => h.noteId !== null && noteIds.includes(h.noteId)).map((h) => h.rect)
  const left = Math.min(...rects.map((r) => r[0]))
  const bottom = Math.max(...rects.map((r) => r[3]))
  return { left: left * scale, top: (bottom + HOVER_CARD_GAP_PT) * scale }
}

export function ReaderPage({ paperId }: { paperId: string }) {
  const { doc, error: pdfError } = usePdfDocument(api.paperFileUrl(paperId))
  const paper = usePaper(paperId)
  const notesQuery = useNotes(paperId)
  const mutations = useNoteMutations(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const [draft, setDraft] = useState<SelectionAnchor | null>(null)
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const [hover, setHover] = useState<Hover | null>(null)
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

  function captureSelection() {
    const result = readSelection(scale)
    if (result.kind === 'invalid') setError(result.reason)
    if (result.kind === 'anchor') {
      setError(null)
      setDraft(result.anchor)
    }
  }

  async function saveDraft(body: string): Promise<boolean> {
    if (!draft) return false
    const anchor = { paper_id: paperId, page: draft.page, bbox: draft.rects, quoted_text: draft.quotedText }
    const saved = await attempt(() => mutations.create.mutateAsync({ body, anchor }))
    if (saved) {
      setDraft(null)
      window.getSelection()?.removeAllRanges()
    }
    return saved
  }

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

  /** Shows the notes under the pointer and scrolls the panel to the first, only when that set changes. */
  function trackHover(event: MouseEvent) {
    const pageElement = (event.target as Element).closest<HTMLElement>('.pdf-page')
    const pageNumber = Number(pageElement?.dataset.page)
    const noteIds =
      pageElement && event.buttons === 0 // no preview while dragging a selection
        ? notesAt(
            highlightsByPage.get(pageNumber) ?? [],
            clientPointToPdf({ x: event.clientX, y: event.clientY }, pageElement.getBoundingClientRect(), scale),
          )
        : []
    const next = noteIds.length > 0 ? { page: pageNumber, noteIds } : null
    if (next?.page === hover?.page && next?.noteIds.join() === hover?.noteIds.join()) return

    setHover(next)
    if (!next) return
    setActiveNoteId(next.noteIds[0])
    document
      .querySelector(`article.note[data-note-id="${next.noteIds[0]}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

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
        onMouseLeave={() => setHover(null)}
      >
        {doc &&
          Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale}>
              {(highlightsByPage.get(pageNumber) ?? []).map((h) => (
                <div
                  key={h.key}
                  data-note-id={h.noteId ?? undefined}
                  className={cn(
                    'highlight absolute rounded-xs bg-highlight mix-blend-multiply',
                    h.noteId === null && 'draft bg-highlight-draft',
                    h.noteId !== null && h.noteId === activeNoteId && 'active bg-highlight-active',
                  )}
                  style={pdfRectToCss(h.rect, scale)}
                />
              ))}
              {hover?.page === pageNumber && hoveredNotes.length > 0 && (
                <NoteHoverCard
                  notes={hoveredNotes}
                  paperId={paperId}
                  style={hoverCardPosition(highlightsByPage.get(pageNumber) ?? [], hover.noteIds, scale)}
                />
              )}
            </PdfPage>
          ))}
      </section>

      <NotesPanel
        paperId={paperId}
        notes={notes}
        draft={draft}
        activeNoteId={activeNoteId}
        onSaveDraft={saveDraft}
        onCancelDraft={() => setDraft(null)}
        onSelectNote={focusNote}
        onUpdateNote={(note, body) => attempt(() => mutations.update.mutateAsync({ id: note.id, body }))}
        onDeleteNote={deleteNote}
      />
    </div>
  )
}
