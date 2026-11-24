import { Fragment, type ComponentProps } from 'react'
import { Table2 } from 'lucide-react'
import type { Note, NoteKind } from '@/entities'
import type { TableMark } from '@/features/datasets/pageMarks'
import { cn } from '@/lib/utils'
import { pdfRectToCss } from '@/lib/coords'
import { highlightFill } from '@/components/highlightColors'
import { NumberMarks } from '@/features/datasets/NumberMarks'
import type { useLensReader } from '@/features/lenses/useLensReader'
import { LensFade } from '@/features/lenses/LensFade'
import { NoteHoverCard } from '@/features/notes/NoteHoverCard'
import { CitationCard } from '@/features/reader/CitationCard'
import { CitationLinks } from '@/features/reader/CitationLinks'
import type { Citation } from '@/features/reader/citations'
import type { HoverTarget } from '@/features/reader/useHoverCard'
import type { NoteDraft } from '@/features/reader/selection'
import { SelectionCopyButton } from '@/features/reader/SelectionCopyButton'
import type { PageHighlight } from '@/features/reader/pageHighlights'
import { hoverCardPosition, noteRects } from '@/features/reader/pageHighlights'
import type { Flash } from '@/features/reader/useFlash'
import type { PdfRect } from '@/lib/coords'
import { useReaderPointer } from '@/pages/reader/useReaderPointer'

type Pointer = ReturnType<typeof useReaderPointer>

type Props = {
  paperId: string
  pageNumber: number
  scale: number
  lensReader: ReturnType<typeof useLensReader>
  /** This page's highlights, table and number marks. */
  highlights: PageHighlight[]
  tableMarks: TableMark[]
  numberMarks: ComponentProps<typeof NumberMarks>['marks']
  activeNoteId: string | null
  draft: NoteDraft | null
  onCopyQuote: (text: string) => Promise<boolean>
  /** The region being captured, if it is on this page. */
  captureBox: { page: number; rect: PdfRect } | null
  flash: Flash | null
  hover: HoverTarget | null
  hoveredNotes: Note[]
  hoverCard: Pointer['hoverCard']
  setNoteEditing: (noteId: string, editing: boolean) => void
  onUpdateNote: (note: Note, body: string, kind?: NoteKind | null) => Promise<boolean>
  onColorNote: (note: Note, color: string) => Promise<boolean>
  onDeleteNote: (note: Note) => Promise<void>
  citations: Citation[]
  references: ComponentProps<typeof CitationCard>['references']
  onOpenReferences: () => void
  leaveCard: () => void
  focusCitation: (citation: Citation) => void
  closeCitationCard: (citation: Citation) => void
  jumpTo: (citation: Citation, viaKeyboard: boolean) => void
}

/** What sits over one PDF page: highlights, marks, the draft's copy button, the capture box, the flash, the hover cards and citation links. */
export function ReaderPageLayers(props: Props) {
  const { paperId, pageNumber, scale, lensReader, highlights, tableMarks, numberMarks, activeNoteId, draft, hover, hoveredNotes } = props
  const { hoverCard, setNoteEditing, onUpdateNote, onColorNote, onDeleteNote, citations, references, onOpenReferences } = props
  const { leaveCard, focusCitation, closeCitationCard, jumpTo, onCopyQuote, captureBox, flash } = props
  return (
    <>
      <LensFade rects={lensReader.fadeOn(pageNumber)} scale={scale} />
      {highlights.map((h) => (
        <div
          key={h.key}
          data-note-id={h.noteId ?? undefined}
          className={cn(
            'highlight absolute rounded-xs',
            h.figure ? 'figure bg-transparent outline-2' : 'mix-blend-multiply',
            h.noteId === null && 'draft bg-highlight-draft',
            // An outline, not a colour swap: any colour can be the note's own.
            h.noteId !== null && h.noteId === activeNoteId && 'active outline-2 outline-offset-1 outline-primary',
          )}
          style={{
            ...pdfRectToCss(h.rect, scale),
            ...(h.figure ? { outlineColor: h.noteId === activeNoteId ? undefined : (h.color ?? undefined) } : { backgroundColor: h.color ? highlightFill(h.color, h.provenance) : undefined }),
          }}
        />
      ))}
      {tableMarks.map((mark) => (
        <Fragment key={mark.datasetId}>
          <div className="table-region absolute rounded-xs outline-1 outline-primary/40" style={pdfRectToCss(mark.region, scale)} />
          {/* Fixed light colours: the marker sits on the paper, which stays white in both themes. */}
          <div className="table-marker absolute grid place-items-center rounded-xs bg-white/90 ring-1 ring-blue-600/40" style={pdfRectToCss(mark.marker, scale)}>
            <Table2 aria-hidden className="size-3.5 text-blue-600" />
          </div>
        </Fragment>
      ))}
      <NumberMarks marks={numberMarks} scale={scale} />
      {draft?.page === pageNumber && draft.rects.length > 0 && !draft.figure && (
        <SelectionCopyButton
          style={{
            left: draft.rects[draft.rects.length - 1][0] * scale,
            top: draft.rects[draft.rects.length - 1][3] * scale + 4,
          }}
          onCopy={() => onCopyQuote(draft.quotedText)}
        />
      )}
      {captureBox?.page === pageNumber && (
        <div className="capture-box absolute bg-primary/10 outline-2 outline-primary" style={pdfRectToCss(captureBox.rect, scale)} />
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
          style={hoverCardPosition(noteRects(highlights, hover.noteIds), scale)}
          editNoteId={hover.editNoteId}
          onPointerEnter={hoverCard.stay}
          onPointerLeave={hoverCard.leave}
          onEditingChange={setNoteEditing}
          onUpdate={onUpdateNote}
          onColorChange={onColorNote}
          onDelete={onDeleteNote}
        />
      )}
      <CitationLinks
        citations={citations}
        scale={scale}
        openId={hover?.kind === 'citation' && hover.page === pageNumber ? hover.citationId : null}
        renderCard={(citation) => (
          <CitationCard
            citation={citation}
            references={references}
            style={hoverCardPosition([citation.rect], scale)}
            onPointerEnter={hoverCard.stay}
            onPointerLeave={leaveCard}
            onOpenReferences={onOpenReferences}
          />
        )}
        onFocusIn={focusCitation}
        onFocusOut={closeCitationCard}
        onEscape={closeCitationCard}
        onJump={(citation) => jumpTo(citation, true)}
      />
    </>
  )
}
