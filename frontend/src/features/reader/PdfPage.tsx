import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { TextLayerBuilder, type PDFDocumentProxy, type PDFPageProxy } from './pdfjs'

type Props = {
  doc: PDFDocumentProxy
  pageNumber: number
  scale: number
  /** Rendered between the canvas and the text layer, positioned in CSS pixels of this page. */
  children?: ReactNode
}

type Size = { width: number; height: number }
type RenderTask = ReturnType<PDFPageProxy['render']>

const US_LETTER: Size = { width: 612, height: 792 }

export function PdfPage({ doc, pageNumber, scale, children }: Props) {
  const pageRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textLayerRef = useRef<HTMLDivElement>(null)
  const [pointSize, setPointSize] = useState<Size | null>(null)
  const [nearViewport, setNearViewport] = useState(false)
  // The canvas fades in once drawn; until then it is blank anyway (a zoom clears it), so nothing flashes.
  const [drawn, setDrawn] = useState(false)

  // Page size is cheap to read, so every page gets its real height up front and scrolling
  // to a note on page 12 lands in the right place before pages 1-11 have rendered.
  useEffect(() => {
    let active = true
    doc.getPage(pageNumber).then((page) => {
      const { width, height } = page.getViewport({ scale: 1 })
      if (active) setPointSize({ width, height })
    }, console.error)
    return () => {
      active = false
    }
  }, [doc, pageNumber])

  // Canvases are memory-hungry; only pages within a screen of the viewport render.
  useEffect(() => {
    const page = pageRef.current!
    const observer = new IntersectionObserver(([entry]) => setNearViewport(entry.isIntersecting), {
      root: page.parentElement,
      rootMargin: '100% 0px',
    })
    observer.observe(page)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!nearViewport) return
    let active = true
    let renderTask: RenderTask | null = null
    let textLayer: TextLayerBuilder | null = null
    const canvas = canvasRef.current!

    doc
      .getPage(pageNumber)
      .then(async (page) => {
        if (!active) return
        const viewport = page.getViewport({ scale })
        const ratio = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        renderTask = page.render({ canvas, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] })

        // TextLayerBuilder rather than bare TextLayer: it carries PDF.js's fix for
        // selections that jump across the page when the pointer crosses a gap.
        textLayer = new TextLayerBuilder({
          pdfPage: page,
          onAppend: (div: HTMLDivElement) => textLayerRef.current?.replaceChildren(div),
        })
        // The types mark `images` as required; the runtime treats it as optional.
        const textLayerOptions = { viewport } as Parameters<TextLayerBuilder['render']>[0]
        await Promise.all([renderTask.promise, textLayer.render(textLayerOptions)])
        if (active) setDrawn(true)
      })
      .catch((error: Error) => {
        if (active && error.name !== 'RenderingCancelledException') console.error(`page ${pageNumber}`, error)
      })

    return () => {
      active = false
      setDrawn(false)
      renderTask?.cancel()
      textLayer?.cancel()
      canvas.width = 0
      canvas.height = 0
    }
  }, [doc, pageNumber, scale, nearViewport])

  const size = pointSize ?? US_LETTER
  const box = { width: size.width * scale, height: size.height * scale }
  return (
    // Block layout + auto margins (not flex centering) so a page wider than the pane can still be
    // scrolled to its left edge. No border or padding: either would shift selection coordinates.
    // The page stays white in dark mode; it is the paper.
    <div
      ref={pageRef}
      className="pdf-page relative mx-auto mb-4 bg-white shadow-md"
      data-page={pageNumber}
      style={{ ...box, '--total-scale-factor': scale } as CSSProperties}
    >
      <canvas
        ref={canvasRef}
        className={cn('transition-opacity duration-300 ease-out motion-reduce:transition-none', drawn ? 'opacity-100' : 'opacity-0')}
        style={box}
      />
      <div className="pdf-overlay pointer-events-none absolute inset-0">{children}</div>
      <div ref={textLayerRef} />
    </div>
  )
}
