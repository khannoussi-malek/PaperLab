import { useState } from 'react'
import { api } from '@/api/client'
import { usePaper } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { PdfPage } from './PdfPage'
import { ReaderToolbar } from './ReaderToolbar'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

export function ReaderPage({ paperId }: { paperId: string }) {
  const { doc, error: pdfError } = usePdfDocument(api.paperFileUrl(paperId))
  const paper = usePaper(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const scale = ZOOM_STEPS[zoomIndex]

  const shownError = paper.error?.message ?? pdfError
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)_360px] grid-rows-[auto_minmax(0,1fr)]">
      <ReaderToolbar title={paper.data?.title} zoomIndex={zoomIndex} onZoomChange={setZoomIndex} />

      {shownError && (
        <Alert variant="destructive" className="fixed bottom-4 left-4 z-10 w-auto max-w-md shadow-lg">
          <AlertDescription>{shownError}</AlertDescription>
        </Alert>
      )}

      <section className="overflow-auto bg-muted p-4">
        {doc &&
          Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale} />
          ))}
      </section>

      {/* Notes panel column; filled in by Task 6. */}
      <aside className="border-l" />
    </div>
  )
}
