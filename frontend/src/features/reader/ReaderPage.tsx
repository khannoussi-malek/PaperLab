import { Table2 } from 'lucide-react'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { api, type Note } from '@/api/client'
import {
  useChunksOnPage,
  useDataset,
  useNoteMutations,
  useNotes,
  usePaper,
  usePaperDatasets,
  useReferences,
} from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { copyText } from '@/lib/clipboard'
import { readerHref, type ReaderTab, type ReaderTarget } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChatPanel } from '../chat/ChatPanel'
import { AddNumberDialog } from '../data/AddNumberDialog'
import { CaptureTableDialog } from '../data/CaptureTableDialog'
import { DataPanel } from '../data/DataPanel'
import { NumberMarks } from '../data/NumberMarks'
import { numberMarks, tableMarkerAt, tableMarks } from '../data/pageMarks'
import { useCaptureDrag } from '../data/useCaptureDrag'
import { SimilarTab } from '../discovery/SimilarTab'
import { browserStorage, highlightFill, loadLastColor, saveLastColor } from '../notes/highlightColors'
import { NoteHoverCard } from '../notes/NoteHoverCard'
import { NotesPanel } from '../notes/NotesPanel'
import { ReferencesTab } from '../references/ReferencesTab'
import { CitationCard } from './CitationCard'
import { CitationLinks } from './CitationLinks'
import type { Citation } from './citations'
import { pdfRectToCss, type PdfRect } from './coords'
import { MAX_PANEL_SHARE, MIN_PANEL_WIDTH, loadPanelWidth, savePanelWidth } from './panelWidth'
import { citationAt, clientPointToPdf, notesAt, rectContains } from './hitTest'
import { PdfPage } from './PdfPage'
import { ReaderContextMenu, type ContextMenuState } from './ReaderContextMenu'
import { ReaderToolbar } from './ReaderToolbar'
import { RetractionBanner } from './RetractionBanner'
import { RightPanel } from './RightPanel'
import { readSelection, type SelectionAnchor } from './selection'
import { useCitations } from './useCitations'
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

/** The rects of these notes' highlights on one page. */
const noteRects = (highlights: PageHighlight[], noteIds: string[]) =>
  highlights.filter((h) => h.noteId !== null && noteIds.includes(h.noteId)).map((h) => h.rect)

/** Places a hover card just below the lowest of `rects` (the hovered notes', or a citation's link), aligned with the leftmost. */
function hoverCardPosition(rects: PdfRect[], scale: number) {
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
  const [numberDraft, setNumberDraft] = useState<SelectionAnchor | null>(null)
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
  const citationsByPage = useCitations(doc)
  // D149: fetched as soon as the pass finds a citation, so the first hover is instant. A read only (the References tab
  // still queues the first lookup, D78), and the tab shares its cache.
  const references = useReferences(paperId, 'cites', citationsByPage.size > 0)
  const [overCitation, setOverCitation] = useState(false)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [flash, setFlash] = useState<Flash | null>(null)
  const promotedNoteId = useRef<string | null>(null)
  const shownTargetId = useRef<string | null>(null)
  const targetChunks = useChunksOnPage(paperId, target?.kind === 'chunk' ? target.page : null)
  const [error, setError] = useState<string | null>(null)
  const [panelWidth, setPanelWidth] = useState(() => loadPanelWidth(browserStorage()))
  const scale = ZOOM_STEPS[zoomIndex]
  const datasets = usePaperDatasets(paperId)
  const tableMarksByPage = useMemo(() => tableMarks(datasets.data ?? []), [datasets.data])
  const numbersDatasetId = datasets.data?.find((d) => d.kind === 'numbers')?.id ?? null
  const numbersDataset = useDataset(numbersDatasetId)
  const numberMarksByPage = useMemo(() => numberMarks(numbersDataset.data), [numbersDataset.data])
  const captureDrag = useCaptureDrag(scale)
  const { capturing, capture } = captureDrag

  useEffect(() => savePanelWidth(browserStorage(), panelWidth), [panelWidth])
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])

  const highlightsByPage = useMemo(() => groupHighlights(notes, draft, paperId), [notes, draft, paperId])

  // Rendering the flash first gives the scroll a target, even on a page whose canvas hasn't rendered yet.
  // A flash asked for before the PDF has loaded (Show in paper clicked straight after opening) waits for `doc`,
  // since until then no page exists to draw it on or scroll to.
  useEffect(() => {
    if (!flash || !doc) return
    scrollToElement('.chunk-flash', 'center')
    const timer = window.setTimeout(() => setFlash(null), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [flash, doc])

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
    } else if (target.kind === 'region') {
      flashChunk(target.page, target.rects)
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

  /** A citation's click, or Enter on its button: to its entry in the reference list, by the one scroll path (D147). */
  function jumpTo(citation: Citation) {
    hoverCard.close()
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
    if (citation) jumpTo(citation)
    else if (tableMarkerAt(tableMarksByPage.get(where.page) ?? [], where.point)) showTab('data')
  }

  function captureSelection(event: MouseEvent) {
    if (capturing) return captureDrag.endDrag(event)
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

  function focusNote(note: Pick<Note, 'id'>) {
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
    hoverCard.open({ kind: 'notes', page: anchor.page, noteIds: [note.id], editNoteId: note.id })
    // Same race as focusComposer: the closing menu's focus scope can steal focus back from the new textarea.
    // Scoped to this note: another note's hover or panel card can also have an "Edit note" textarea open.
    window.setTimeout(() =>
      document
        .querySelector<HTMLTextAreaElement>(`.note-hover-card [data-note-id="${note.id}"] textarea[aria-label="Edit note"]`)
        ?.focus(),
    )
  }

  function copyToClipboard(text: string) {
    copyText(text).catch((reason: Error) => setError(reason.message))
  }

  function focusComposer() {
    // After the menu has finished closing, or its focus handling takes focus straight back.
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Note"]')?.focus())
  }

  /** Both entry points (the draft menu and the composer) open the dialog on the pending selection. */
  function addNumberFromDraft() {
    setNumberDraft(draft)
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
      setMenu({ x: event.clientX, y: event.clientY, target: { kind: 'draft', quote: pending.quotedText } })
    }
  }

  const hover = hoverCard.target
  const hoveredNotes = hover?.kind === 'notes' ? notes.filter((note) => hover.noteIds.includes(note.id)) : []

  const shownError = error ?? paper.error?.message ?? notesQuery.error?.message ?? pdfError
  return (
    <div
      className={cn('reader grid h-dvh grid-rows-[auto_minmax(0,1fr)]', fadeIn)}
      // CSS clamps too, so a stored width still fits after the window shrinks; the handle clamps as it drags.
      style={{ gridTemplateColumns: `minmax(0,1fr) clamp(${MIN_PANEL_WIDTH}px, ${panelWidth}px, ${MAX_PANEL_SHARE * 100}vw)` }}
    >
      {/* One grid row either way, so the pages and the panel keep their row whether or not the banner shows. */}
      <div className="col-span-full">
        <ReaderToolbar
          paper={paper.data}
          zoomIndex={zoomIndex}
          onZoomChange={setZoomIndex}
          capturing={capturing}
          onCaptureChange={captureDrag.setCapturing}
        />
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
        className={cn(
          'overflow-auto p-4',
          capturing && 'cursor-crosshair select-none',
          // PDF.js's own stylesheet gives the text layer a text cursor, unlayered: only an !important utility beats it.
          overCitation && !capturing && 'cursor-pointer [&_.textLayer_span]:cursor-pointer!',
        )}
        onMouseDown={captureDrag.startDrag}
        onMouseUp={captureSelection}
        onClick={handlePageClick}
        onMouseMove={capturing ? captureDrag.moveDrag : trackHover}
        onMouseLeave={leaveCard}
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
              {(tableMarksByPage.get(pageNumber) ?? []).map((mark) => (
                <Fragment key={mark.datasetId}>
                  <div className="table-region absolute rounded-xs outline-1 outline-primary/40" style={pdfRectToCss(mark.region, scale)} />
                  {/* Fixed light colours: the marker sits on the paper, which stays white in both themes. */}
                  <div className="table-marker absolute grid place-items-center rounded-xs bg-white/90 ring-1 ring-blue-600/40" style={pdfRectToCss(mark.marker, scale)}>
                    <Table2 aria-hidden className="size-3.5 text-blue-600" />
                  </div>
                </Fragment>
              ))}
              <NumberMarks marks={numberMarksByPage.get(pageNumber) ?? []} scale={scale} />
              {captureDrag.box?.page === pageNumber && (
                <div className="capture-box absolute bg-primary/10 outline-2 outline-primary" style={pdfRectToCss(captureDrag.box.rect, scale)} />
              )}
              {flash?.page === pageNumber &&
                flash.rects.map((rect, r) => (
                  <div
                    key={`${flash.id}-${r}`}
                    className="chunk-flash absolute rounded-xs bg-highlight-draft outline-2 outline-offset-1 outline-primary mix-blend-multiply motion-safe:animate-pulse"
                    style={pdfRectToCss(rect, scale)}
                  />
                ))}
              {hover?.kind === 'notes' && hover.page === pageNumber && hoveredNotes.length > 0 && (
                <NoteHoverCard
                  notes={hoveredNotes}
                  paperId={paperId}
                  style={hoverCardPosition(noteRects(highlightsByPage.get(pageNumber) ?? [], hover.noteIds), scale)}
                  editNoteId={hover.editNoteId}
                  onPointerEnter={hoverCard.stay}
                  onPointerLeave={hoverCard.leave}
                  onEditingChange={setNoteEditing}
                  onUpdate={updateNoteBody}
                  onColorChange={recolorNote}
                  onDelete={deleteNote}
                />
              )}
              <CitationLinks
                citations={citationsByPage.get(pageNumber) ?? []}
                scale={scale}
                openId={hover?.kind === 'citation' && hover.page === pageNumber ? hover.citationId : null}
                renderCard={(citation) => (
                  <CitationCard
                    citation={citation}
                    paperId={paperId}
                    references={references}
                    style={hoverCardPosition([citation.rect], scale)}
                    onPointerEnter={hoverCard.stay}
                    onPointerLeave={leaveCard}
                    onOpenReferences={() => showTab('references')}
                  />
                )}
                onFocusIn={focusCitation}
                onFocusOut={closeCitationCard}
                onEscape={closeCitationCard}
                onJump={jumpTo}
              />
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
            onAddNumber={addNumberFromDraft}
            onSelectNote={focusNote}
            onUpdateNote={updateNoteBody}
            onColorNote={recolorNote}
            onDeleteNote={deleteNote}
          />
        }
        chat={
          <ChatPanel
            scope={{ kind: 'paper', id: paperId }}
            // A cited passage flashes on its page; a cited note is focused as if picked in the Notes tab.
            onCite={(source) => ('bbox' in source ? flashChunk(source.page, source.bbox) : focusNote({ id: source.note_id }))}
            onPromoted={showPromotedNote}
          />
        }
        data={<DataPanel paperId={paperId} onShowRegion={flashChunk} />}
        similar={<SimilarTab paperId={paperId} active={tab === 'similar'} />}
        references={<ReferencesTab paperId={paperId} active={tab === 'references'} />}
      />

      {numberDraft && (
        <AddNumberDialog
          paperId={paperId}
          anchor={numberDraft}
          onClose={() => {
            setNumberDraft(null)
            setDraft(null)
          }}
        />
      )}

      {capture && doc && (
        <CaptureTableDialog
          paperId={paperId}
          doc={doc}
          page={capture.page}
          region={capture.region}
          onClose={captureDrag.closeCapture}
          onSaved={() => {
            captureDrag.closeCapture()
            showTab('data')
          }}
        />
      )}

      <ReaderContextMenu
        menu={menu}
        onClose={() => setMenu(null)}
        onColorNote={(note, color) => void recolorNote(note, color)}
        onEditNote={editNote}
        onDeleteNote={(note) => void deleteNote(note)}
        onHighlightDraft={(color) => void highlightDraft(color)}
        onAddNote={focusComposer}
        onAddNumber={addNumberFromDraft}
        onCancelDraft={() => setDraft(null)}
        onCopy={copyToClipboard}
      />
    </div>
  )
}
