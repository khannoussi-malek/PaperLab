import { useEffect, useState, type MouseEvent } from 'react'
import type { PdfRect } from '../reader/coords'
import { clientPointToPdf } from '../reader/hitTest'
import { dragRegion } from './pageMarks'

type Point = [number, number]
type Drag = { page: number; start: Point; end: Point }

/** The pointer in PDF points on a rendered page, kept on that page even when it strays off it. */
function pointKeptOnPage(event: MouseEvent, page: HTMLElement, scale: number) {
  const box = page.getBoundingClientRect()
  const size = { width: box.width / scale, height: box.height / scale }
  const [x, y] = clientPointToPdf({ x: event.clientX, y: event.clientY }, box, scale)
  const point: Point = [Math.min(Math.max(x, 0), size.width), Math.min(Math.max(y, 0), size.height)]
  return { point, size }
}

const pageElement = (page: number) => document.querySelector<HTMLElement>(`.pdf-page[data-page="${page}"]`)

/**
 * The reader's capture mode: while on, a drag on a page draws a box, and releasing it on a table-sized region
 * turns the mode off and hands back `{ page, region }` for the capture dialog. Escape leaves the mode.
 */
export function useCaptureDrag(scale: number) {
  const [capturing, setCapturing] = useState(false)
  const [drag, setDrag] = useState<Drag | null>(null)
  const [capture, setCapture] = useState<{ page: number; region: PdfRect } | null>(null)

  useEffect(() => {
    if (!capturing) return
    const leave = (event: KeyboardEvent) => event.key === 'Escape' && setCapturing(false)
    window.addEventListener('keydown', leave)
    return () => window.removeEventListener('keydown', leave)
  }, [capturing])

  function startDrag(event: MouseEvent) {
    const page = capturing && event.button === 0 ? (event.target as Element).closest<HTMLElement>('.pdf-page') : null
    if (!page) return
    event.preventDefault() // no text selection starts
    const { point } = pointKeptOnPage(event, page, scale)
    setDrag({ page: Number(page.dataset.page), start: point, end: point })
  }

  function moveDrag(event: MouseEvent) {
    const page = drag && pageElement(drag.page)
    if (!drag || !page) return
    if (event.buttons === 0) return setDrag(null) // released outside the pages
    setDrag({ ...drag, end: pointKeptOnPage(event, page, scale).point })
  }

  // Ends at the release point, not the last stored one: the final move may not have rendered yet.
  function endDrag(event: MouseEvent) {
    const page = drag && pageElement(drag.page)
    setDrag(null)
    if (!drag || !page) return
    const { point, size } = pointKeptOnPage(event, page, scale)
    const region = dragRegion(drag.start, point, size)
    if (!region) return
    setCapture({ page: drag.page, region })
    setCapturing(false)
  }

  const box = drag && {
    page: drag.page,
    rect: [
      Math.min(drag.start[0], drag.end[0]),
      Math.min(drag.start[1], drag.end[1]),
      Math.max(drag.start[0], drag.end[0]),
      Math.max(drag.start[1], drag.end[1]),
    ] as PdfRect,
  }

  return { capturing, setCapturing, box, capture, closeCapture: () => setCapture(null), startDrag, moveDrag, endDrag }
}
