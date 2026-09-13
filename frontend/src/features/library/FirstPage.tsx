import { useEffect, useRef, useState } from 'react'
import type { PDFPageProxy } from '@/features/reader/pdfjs'
import { usePdfDocument } from '@/features/reader/usePdfDocument'
import { cn } from '@/lib/utils'

type RenderTask = ReturnType<PDFPageProxy['render']>

/** CSS width the page is rasterised at; matches the preview panel so the canvas is never upscaled. */
const RENDER_WIDTH = 352
const US_LETTER_ASPECT = 612 / 792

/** Page 1 of a PDF as a white sheet. Mount with `key={url}`: one component instance per document. */
export function FirstPage({ url, title }: { url: string; title: string }) {
  const { doc, error } = usePdfDocument(url)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [aspect, setAspect] = useState(US_LETTER_ASPECT)
  const [drawn, setDrawn] = useState(false)

  useEffect(() => {
    if (!doc) return
    let active = true
    let task: RenderTask | null = null
    const canvas = canvasRef.current!

    doc
      .getPage(1)
      .then(async (page) => {
        if (!active) return
        const pointWidth = page.getViewport({ scale: 1 }).width
        const viewport = page.getViewport({ scale: (RENDER_WIDTH * (window.devicePixelRatio || 1)) / pointWidth })
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        setAspect(viewport.width / viewport.height)
        task = page.render({ canvas, viewport })
        await task.promise
        if (active) setDrawn(true)
      })
      .catch((err: Error) => {
        if (active && err.name !== 'RenderingCancelledException') console.error('first page', err)
      })

    return () => {
      active = false
      task?.cancel()
    }
  }, [doc])

  return (
    // The box reserves the page's shape before anything is drawn, so the details below never jump.
    <div className="relative w-full overflow-hidden rounded-sm bg-white shadow-md" style={{ aspectRatio: aspect }}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`First page of ${title}`}
        className={cn('size-full transition-opacity duration-200', drawn ? 'opacity-100' : 'opacity-0')}
      />
      {!drawn && (
        <div
          className={cn(
            'absolute inset-0 grid place-items-center bg-muted/60 p-4 text-center text-sm',
            error ? 'text-destructive' : 'text-muted-foreground motion-safe:animate-pulse',
          )}
        >
          {error ?? 'Loading page…'}
        </div>
      )}
    </div>
  )
}
