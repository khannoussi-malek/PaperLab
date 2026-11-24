import { useEffect, useMemo, useRef, useState } from 'react'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { copyText } from '@/lib/clipboard'
import { readerHref, type ReaderTab, type ReaderTarget } from '@/router/route'
import { cn } from '@/lib/utils'
import { AddNumberDialog } from '@/features/datasets/AddNumberDialog'
import { CaptureTableDialog } from '@/features/datasets/CaptureTableDialog'
import { useCaptureDrag } from '@/features/datasets/useCaptureDrag'
import { LensPicker } from '@/features/lenses/LensPicker'
import { useLensReader } from '@/features/lenses/useLensReader'
import { browserStorage } from '@/components/highlightColors'
import { loadPanelWidth, panelTrack, savePanelWidth } from '@/components/panelWidth'
import { READER_PANEL } from '@/features/reader/panelWidth'
import { ReaderContextMenu } from '@/features/reader/ReaderContextMenu'
import { PaperTagChips } from '@/features/reader/PaperTagChips'
import { ReaderToolbar } from '@/features/reader/ReaderToolbar'
import { ReadingContextBanner } from '@/features/reader/ReadingContextBanner'
import { PublishedVersionBanner } from '@/features/reader/PublishedVersionBanner'
import { RetractionBanner } from '@/features/reader/RetractionBanner'
import { groupHighlights } from '@/features/reader/pageHighlights'
import { ReaderPages } from '@/pages/reader/ReaderPages'
import { ReaderSidePanel } from '@/pages/reader/ReaderSidePanel'
import { useCitations } from '@/features/reader/useCitations'
import { useFlash } from '@/features/reader/useFlash'
import { useNoteComposer } from '@/features/reader/useNoteComposer'
import { useNoteFocus } from '@/features/reader/useNoteFocus'
import { useReaderDocument } from '@/features/reader/useReaderDocument'
import { useReaderMarks } from '@/pages/reader/useReaderMarks'
import { useReaderPointer } from '@/pages/reader/useReaderPointer'
import { useReaderTarget } from '@/features/reader/useReaderTarget'
import { useJumpBack } from '@/features/reader/useJumpBack'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from '@/features/reader/zoom'

export { groupHighlights } from '@/features/reader/pageHighlights'

type Props = {
  paperId: string
  tab: ReaderTab
  /** A chunk to flash or a note to focus once, from the hash. */
  target: ReaderTarget
}

export function ReaderPage({ paperId, tab, target }: Props) {
  const { paper, noPdf, doc, pdfError, notesQuery, notes } = useReaderDocument(paperId)
  const { tableMarksByPage, numberMarksByPage } = useReaderMarks(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const scale = ZOOM_STEPS[zoomIndex]
  const [error, setError] = useState<string | null>(null)
  // replace, not assign: switching tabs shouldn't add history entries for Back to walk through.
  const showTab = (next: ReaderTab) => window.location.replace(readerHref(paperId, next))

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

  const {
    draft, setDraft, wholePaperDraft, setWholePaperDraft, numberDraft, setNumberDraft, draftColor, setDraftColor,
    movedToNotes, setMovedToNotes, blockedByTypedNote, saveDraft, savePaperNote, newPaperNote, paperNoteDirty,
    highlightDraft, updateNoteBody, recolorNote, deleteNote, focusComposer, addNumberFromDraft,
  } = useNoteComposer({ paperId, noPdf, attempt, setError })
  const captureDrag = useCaptureDrag(scale, (page, region) => {
    if (blockedByTypedNote()) return
    setWholePaperDraft(null)
    setDraft({ page, rects: [region], quotedText: `Figure on p. ${page}`, figure: true })
    showTab('notes')
  })
  const { capturing, capture } = captureDrag

  const [panelWidth, setPanelWidth] = useState(() => loadPanelWidth(READER_PANEL, browserStorage()))
  useEffect(() => savePanelWidth(READER_PANEL, browserStorage(), panelWidth), [panelWidth])
  const highlightsByPage = useMemo(() => groupHighlights(notes, draft, paperId), [notes, draft, paperId])

  // Before useFlash: Back's focus (keyboard jump) must run before the flash scrolls to its passage, or it scrolls away.
  const citationsByPage = useCitations(doc)
  const pagesRef = useRef<HTMLElement>(null)
  const jumpBack = useJumpBack(pagesRef, scale)
  const { flash, flashChunk } = useFlash(doc)
  const lensReader = useLensReader(paperId, tab, flashChunk)
  const { activeNoteId, setActiveNoteId, focusNote, showPromotedNote } = useNoteFocus(paperId, tab, notes, showTab)
  useReaderTarget({ paperId, tab, target, doc, noPdf, notesQuery, flashChunk, focusNote })

  const pointer = useReaderPointer({
    paperId, scale, saveJump: (citation, viaKeyboard) => jumpBack.save(citation, viaKeyboard), noPdf, tab, notes, citationsByPage, highlightsByPage, tableMarksByPage, draft, setDraft,
    setWholePaperDraft, setError, blockedByTypedNote, setActiveNoteId, showTab, flashChunk,
    capturing, endCaptureDrag: captureDrag.endDrag,
  })
  const { hoverCard, overCitation, menu, setMenu } = pointer

  /** Answers whether the text reached the clipboard, so a button can show it worked; a refusal goes to the alert. */
  function copyToClipboard(text: string): Promise<boolean> {
    return copyText(text).then(
      () => true,
      (reason: Error) => {
        setError(reason.message)
        return false
      },
    )
  }

  /** The skip link's target: the side panel's tab list, or its first focusable element (the active tab). */
  function focusSidePanel() {
    document.querySelector<HTMLElement>('#reader-panel-tabs [role="tab"]')?.focus()
  }

  const hover = hoverCard.target
  const hoveredNotes = hover?.kind === 'notes' ? notes.filter((note) => hover.noteIds.includes(note.id)) : []

  const shownError = error ?? paper.error?.message ?? notesQuery.error?.message ?? pdfError
  return (
    <div
      className={cn('reader grid h-dvh grid-rows-[auto_minmax(0,1fr)]', fadeIn)}
      // CSS clamps too, so a stored width still fits after the window shrinks; the handle clamps as it drags.
      style={{ gridTemplateColumns: `minmax(0,1fr) ${panelTrack(READER_PANEL, panelWidth)}` }}
    >
      {/* One grid row either way, so the pages and the panel keep their row whether or not the banner shows. */}
      <div className="col-span-full">
        <ReaderToolbar
          paper={paper.data}
          zoomIndex={zoomIndex}
          onZoomChange={setZoomIndex}
          capturing={captureDrag.tableMode}
          onCaptureChange={captureDrag.setCapturing}
          drawingFigure={captureDrag.drawingFigure}
          onDrawingFigureChange={captureDrag.setDrawingFigure}
          onOpenReferences={() => showTab('references')}
          onWriteNote={(kind) => {
            setDraft(null)
            setWholePaperDraft({ kind })
            showTab('notes')
          }}
          onOpenNote={(id) => focusNote({ id })}
          tags={paper.data && <PaperTagChips paperId={paper.data.id} />}
          lensControl={<LensPicker reader={lensReader} />}
        />
        {paper.data?.is_retracted && <RetractionBanner paper={paper.data} />}
        {paper.data?.published_doi && <PublishedVersionBanner paper={paper.data} />}
        {paper.data && <ReadingContextBanner paperId={paperId} />}
      </div>

      {/* Hidden until focused: hundreds of citation buttons sit between the toolbar and the side panel in tab order,
          so a keyboard user can jump straight past all of them. */}
      <button
        type="button"
        onClick={focusSidePanel}
        className={cn(
          glass,
          'sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-20 focus:rounded-full focus:border focus:border-glass-border focus:bg-glass-strong focus:px-3 focus:py-1.5 focus:text-sm focus:font-medium focus:shadow-lg focus:outline-2 focus:outline-primary',
        )}
      >
        Skip to side panel
      </button>

      {shownError && (
        <Alert
          variant="destructive"
          className={cn('fixed bottom-4 left-4 z-10 w-auto max-w-md cursor-pointer border-glass-border shadow-lg', glass)}
          onClick={() => setError(null)}
        >
          <AlertDescription>{shownError}</AlertDescription>
        </Alert>
      )}

      <ReaderPages
        pagesRef={pagesRef}
        doc={doc}
        paper={paper.data}
        noPdf={noPdf}
        scale={scale}
        capturing={capturing}
        overCitation={overCitation}
        captureDrag={captureDrag}
        pointer={pointer}
        jumpBack={jumpBack}
        highlightsByPage={highlightsByPage}
        tableMarksByPage={tableMarksByPage}
        numberMarksByPage={numberMarksByPage}
        citationsByPage={citationsByPage}
        layers={{
          paperId,
          scale,
          lensReader,
          activeNoteId,
          draft,
          onCopyQuote: copyToClipboard,
          captureBox: captureDrag.box,
          flash,
          hover,
          hoveredNotes,
          hoverCard,
          setNoteEditing: pointer.setNoteEditing,
          onUpdateNote: updateNoteBody,
          onColorNote: recolorNote,
          onDeleteNote: deleteNote,
          references: pointer.references,
          onOpenReferences: () => showTab('references'),
          leaveCard: pointer.leaveCard,
          focusCitation: pointer.focusCitation,
          closeCitationCard: pointer.closeCitationCard,
          jumpTo: pointer.jumpTo,
        }}
      />

      <ReaderSidePanel
        paperId={paperId}
        paper={paper.data}
        noPdf={noPdf}
        tab={tab}
        showTab={showTab}
        panelWidth={panelWidth}
        onWidthChange={setPanelWidth}
        lensReader={lensReader}
        notes={notes}
        draft={draft}
        draftColor={draftColor}
        onDraftColorChange={setDraftColor}
        activeNoteId={activeNoteId}
        wholePaperDraft={wholePaperDraft}
        movedToNotes={movedToNotes}
        onMovedToNotesChange={setMovedToNotes}
        onNewPaperNote={newPaperNote}
        onCancelPaperNote={() => setWholePaperDraft(null)}
        onPaperNoteDirty={paperNoteDirty}
        onSavePaperNote={savePaperNote}
        onSaveDraft={saveDraft}
        onCancelDraft={() => setDraft(null)}
        onAddNumber={addNumberFromDraft}
        onSelectNote={focusNote}
        onShowPromotedNote={showPromotedNote}
        onUpdateNote={updateNoteBody}
        onColorNote={recolorNote}
        onDeleteNote={deleteNote}
        onFlashChunk={flashChunk}
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
        onEditNote={pointer.editNote}
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
