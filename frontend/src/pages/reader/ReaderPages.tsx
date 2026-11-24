import type { RefObject } from 'react'
import { Undo2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { glass } from '@/components/glass'
import { popIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { PdfPage } from '@/features/reader/PdfPage'
import { PaperDetailsPanel } from '@/features/reader/PaperDetailsPanel'
import { ReaderPageLayers } from '@/pages/reader/ReaderPageLayers'
import type { PageHighlight } from '@/features/reader/pageHighlights'
import type { Citation } from '@/features/reader/citations'
import type { useCaptureDrag } from '@/features/datasets/useCaptureDrag'
import type { useReaderPointer } from '@/pages/reader/useReaderPointer'
import type { useJumpBack } from '@/features/reader/useJumpBack'
import type { Paper } from '@/entities'
import type { PDFDocumentProxy } from '@/features/reader/pdfjs'
import type { TableMark, NumberMark } from '@/features/datasets/pageMarks'

/** Everything the pages share: what each page's overlays read, and the handlers they call. */
export type SharedLayers = Omit<
  Parameters<typeof ReaderPageLayers>[0],
  'pageNumber' | 'highlights' | 'tableMarks' | 'numberMarks' | 'citations'
>

type Props = {
  pagesRef: RefObject<HTMLElement | null>
  doc: PDFDocumentProxy | null
  paper: Paper | undefined
  noPdf: boolean
  scale: number
  capturing: boolean
  overCitation: boolean
  captureDrag: ReturnType<typeof useCaptureDrag>
  pointer: ReturnType<typeof useReaderPointer>
  jumpBack: ReturnType<typeof useJumpBack>
  highlightsByPage: Map<number, PageHighlight[]>
  tableMarksByPage: Map<number, TableMark[]>
  numberMarksByPage: Map<number, NumberMark[]>
  citationsByPage: Map<number, Citation[]>
  layers: SharedLayers
}

/** The scrolling section: every PDF page with its overlays, the paper's details when it has no PDF, and the jump-back pill. */
export function ReaderPages(props: Props) {
  const { pagesRef, doc, paper, noPdf, scale, capturing, overCitation, captureDrag, pointer } = props
  // Destructured here: the page only passes the jump-back object down, so its fields are read in this component.
  const { spot, pillRef, onScroll, back } = props.jumpBack
  const { highlightsByPage, tableMarksByPage, numberMarksByPage, citationsByPage, layers } = props
  return (
    <section
      ref={pagesRef}
      className={cn(
        'overflow-auto p-4',
        capturing && 'cursor-crosshair select-none',
        // PDF.js's own stylesheet gives the text layer a text cursor, unlayered: only an !important utility beats it.
        overCitation && !capturing && 'cursor-pointer [&_.textLayer_span]:cursor-pointer!',
      )}
      onMouseDown={captureDrag.startDrag}
      onMouseUp={pointer.captureSelection}
      onClick={pointer.handlePageClick}
      onMouseMove={capturing ? captureDrag.moveDrag : pointer.trackHover}
      onMouseLeave={pointer.leaveCard}
      onScroll={onScroll}
      onContextMenu={pointer.openContextMenu}
    >
      {noPdf && paper && <PaperDetailsPanel paper={paper} />}
      {doc &&
        Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
        <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale}>
          <ReaderPageLayers
            {...layers}
            pageNumber={pageNumber}
            highlights={highlightsByPage.get(pageNumber) ?? []}
            tableMarks={tableMarksByPage.get(pageNumber) ?? []}
            numberMarks={numberMarksByPage.get(pageNumber) ?? []}
            citations={citationsByPage.get(pageNumber) ?? []}
          />
        </PdfPage>
        ))}
      {/* The way back from a citation jump, at the foot of the pages while they scroll. No height of its own. */}
      {spot && (
        <div className="pointer-events-none sticky bottom-4 flex h-0 items-end justify-center">
          <Button
            key={spot.id}
            ref={pillRef}
            variant="ghost"
            className={cn(glass, 'pointer-events-auto origin-bottom rounded-full border-glass-border bg-glass-strong shadow-lg', popIn)}
            onClick={back}
          >
            <Undo2 aria-hidden />
            Back to page {spot.page}
          </Button>
        </div>
      )}
    </section>
  )
}
