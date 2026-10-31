import { useEffect, useRef, useState } from 'react'
import { PdfPage } from '@/features/reader/PdfPage'
import { usePdfDocument } from '@/features/reader/usePdfDocument'

const FALLBACK_WIDTH = 560

/** The compiled PDF's one page, scaled to the box width. */
export default function DiagramPreview({ url }: { url: string }) {
  const { doc, error } = usePdfDocument(url)
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState<number | null>(null)
  useEffect(() => {
    if (!doc) return
    let active = true
    doc.getPage(1).then((page) => {
      if (active) setScale((box.current?.clientWidth || FALLBACK_WIDTH) / page.getViewport({ scale: 1 }).width)
    }, console.error)
    return () => { active = false }
  }, [doc])
  return (
    <div ref={box} role="img" aria-label="Diagram preview" className="overflow-auto rounded-lg border border-glass-border">
      {error ? <p className="p-2 text-sm text-destructive">{"Couldn't show the preview."}</p> : doc && scale && <PdfPage doc={doc} pageNumber={1} scale={scale} />}
    </div>
  )
}
