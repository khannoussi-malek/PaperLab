import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { api, type Note } from '@/api/client'
import { useChunksOnPage, useNoteMutations, useNotes, usePaper } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { readerHref, type ReaderTab, type ReaderTarget } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChatPanel } from '../chat/ChatPanel'
import { browserStorage, highlightFill, loadLastColor, saveLastColor } from '../notes/highlightColors'
import { NoteHoverCard } from '../notes/NoteHoverCard'
import { NotesPanel } from '../notes/NotesPanel'
import { pdfRectToCss, type PdfRect } from './coords'
import { MAX_PANEL_SHARE, MIN_PANEL_WIDTH, loadPanelWidth, savePanelWidth } from './panelWidth'
import { clientPointToPdf, notesAt, rectContains } from './hitTest'
import { PdfPage } from './PdfPage'
import { ReaderContextMenu, type ContextMenuState } from './ReaderContextMenu'
import { ReaderToolbar } from './ReaderToolbar'
import { RetractionBanner } from './RetractionBanner'
import { RightPanel } from './RightPanel'
import { readSelection, type SelectionAnchor } from './selection'
import { useHoverCard } from './useHoverCard'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

/** One drawn rect. `color` is its note's colour, or null for the pending selection (drawn with the draft token). */
type PageHighlight = { key: string; noteId: string | null; color: string | null; provenance?: Note['provenance']; rect: PdfRect }

function groupHighlights(notes: Note[], draft: SelectionAnchor | null, paperId: string) {
  const byPage = new Map<number, PageHighlight[]>()
  const add = (page: number, highlight: PageHighlight) =>
    byPage.set(page, [...(byPage.get(page) ?? []), highlight])

  for (const note of notes) {
    note.anchors.forEach((anchor, a) => {
      if (anchor.paper_id !== paperId) return
      anchor.bbox.forEach((rect, r) =>
        add(anchor.page, { key: `${note.id}-${a}-${r}`, noteId: note.id, color: note.color, provenance: note.provenance, rect }),
      )
    })
  }
  draft?.rects.forEach((rect, r) => add(draft.page, { key: `draft-${r}`, noteId: null, color: null, rect }))
  return byPage
}

const HOVER_CARD_GAP_PT = 4
const FLASH_MS = 1500

/** A cited chunk being shown; `id` restarts the flash when the same citation is clicked again. */
type Flash = { id: number; page: number; rects: PdfRect[] }

/** The reader's one scroll path: notes, hovered highlights and cited chunks are all brought into view with it. */
function scrollToElement(selector: string, block: ScrollLogicalPosition) {
  document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block })
}

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

type Props = {
  paperId: string
  tab: ReaderTab
  /** A chunk to flash or a note to focus once, from the hash. */
  target: ReaderTarget
}

export function ReaderPage({ paperId, tab, target }: Props) {
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
  const [flash, setFlash] = useState<Flash | null>(null)
  const promotedNoteId = useRef<string | null>(null)
  const shownTargetId = useRef<string | null>(null)
  const targetChunks = useChunksOnPage(paperId, target?.kind === 'chunk' ? target.page : null)
  const [error, setError] = useState<string | null>(null)
  const [panelWidth, setPanelWidth] = useState(() => loadPanelWidth(browserStorage()))
  const scale = ZOOM_STEPS[zoomIndex]

  useEffect(() => savePanelWidth(browserStorage(), panelWidth), [panelWidth])
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])

  const highlightsByPage = useMemo(() => groupHighlights(notes, draft, paperId), [notes, draft, paperId])

  // Rendering the flash first gives the scroll a target, even on a page whose canvas hasn't rendered yet.
  useEffect(() => {
    if (!flash) return
    scrollToElement('.chunk-flash', 'center')
    const timer = window.setTimeout(() => setFlash(null), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [flash])

  const flashChunk = (page: number, rects: PdfRect[]) => setFlash({ id: Date.now(), page, rects })

  // Once the Notes tab is showing, bring a just-promoted note's card into view.
  useEffect(() => {
    if (tab !== 'notes' || !promotedNoteId.current) return
    scrollToElement(`article.note[data-note-id="${promotedNoteId.current}"]`, 'nearest')
    promotedNoteId.current = null
  }, [tab])

  // replace, not assign: switching tabs shouldn't add history entries for Back to walk through.
  const showTab = (next: ReaderTab) => window.location.replace(readerHref(paperId, next))

  // A one-shot target from the hash. Once the PDF and what the target needs have loaded, it goes
  // through the same path as a citation click or a note click, then leaves the hash so a reload doesn't repeat it.
  // replaceState fires no hashchange and adds no history entry, so Back still returns to where the link was.
  useEffect(() => {
    if (!doc || !target || shownTargetId.current === target.id) return
    if (target.kind === 'chunk') {
      if (!targetChunks.data) return
      const chunk = targetChunks.data.find((c) => c.id === target.id)
      if (chunk) flashChunk(chunk.page, chunk.bbox)
    } else {
      if (!notesQuery.data) return
      const note = notesQuery.data.find((n) => n.id === target.id)
      if (note) focusNote(note)
    }
    shownTargetId.current = target.id
    window.history.replaceState(null, '', readerHref(paperId, tab))
  })

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
      if (tab !== 'notes') showTab('notes') // the composer lives on the Notes tab
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
    scrollToElement(`.highlight[data-note-id="${note.id}"]`, 'center')
  }

  function showPromotedNote(note: Note) {
    setActiveNoteId(note.id)
    promotedNoteId.current = note.id
    showTab('notes')
  }

  function editNote(note: Note) {
    const anchor = note.anchors.find((a) => a.paper_id === paperId)
    if (!anchor) return
    hoverCard.open({ page: anchor.page, noteIds: [note.id], editNoteId: note.id })
    // Same race as focusComposer: the closing menu's focus scope can steal focus back from the new textarea.
    // Scoped to this note: another note's hover or panel card can also have an "Edit note" textarea open.
    window.setTimeout(() =>
      document
        .querySelector<HTMLTextAreaElement>(`.note-hover-card [data-note-id="${note.id}"] textarea[aria-label="Edit note"]`)
        ?.focus(),
    )
  }

  function copyText(text: string) {
    if (!navigator.clipboard) return setError('Copying needs clipboard access, which this browser blocks here.')
    navigator.clipboard.writeText(text).catch(() => setError('Could not copy: the browser blocked clipboard access.'))
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
    scrollToElement(`article.note[data-note-id="${noteIds[0]}"]`, 'nearest')
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
    <div
      className={cn('reader grid h-dvh grid-rows-[auto_minmax(0,1fr)]', fadeIn)}
      // CSS clamps too, so a stored width still fits after the window shrinks; the handle clamps as it drags.
      style={{ gridTemplateColumns: `minmax(0,1fr) clamp(${MIN_PANEL_WIDTH}px, ${panelWidth}px, ${MAX_PANEL_SHARE * 100}vw)` }}
    >
      {/* One grid row either way, so the pages and the panel keep their row whether or not the banner shows. */}
      <div className="col-span-full">
        <ReaderToolbar paper={paper.data} zoomIndex={zoomIndex} onZoomChange={setZoomIndex} />
        {paper.data?.is_retracted && <RetractionBanner paper={paper.data} />}
      </div>

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
                  style={{ ...pdfRectToCss(h.rect, scale), backgroundColor: h.color ? highlightFill(h.color, h.provenance) : undefined }}
                />
              ))}
              {flash?.page === pageNumber &&
                flash.rects.map((rect, r) => (
                  <div
                    key={`${flash.id}-${r}`}
                    className="chunk-flash absolute rounded-xs bg-highlight-draft outline-2 outline-offset-1 outline-primary mix-blend-multiply motion-safe:animate-pulse"
                    style={pdfRectToCss(rect, scale)}
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

      <RightPanel
        tab={tab}
        onTabChange={showTab}
        width={panelWidth}
        onWidthChange={setPanelWidth}
        notes={
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
        }
        chat={
          <ChatPanel
            scope={{ kind: 'paper', id: paperId }}
            // Single-paper answers cite only passages ('bbox' in source); their notes list is always empty.
            onCite={(source) => 'bbox' in source && flashChunk(source.page, source.bbox)}
            onPromoted={showPromotedNote}
          />
        }
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
        onCopy={copyText}
      />
    </div>
  )
}
