import { clientRectsToPdfRects, type PdfRect } from './coords'

export type SelectionAnchor = { page: number; rects: PdfRect[]; quotedText: string }

export type SelectionResult =
  | { kind: 'none' }
  | { kind: 'invalid'; reason: string }
  | { kind: 'anchor'; anchor: SelectionAnchor }

const pageElementOf = (node: Node) =>
  (node instanceof Element ? node : node.parentElement)?.closest<HTMLElement>('.pdf-page') ?? null

/** Reads the browser selection as an anchor in PDF points on a single page. */
export function readSelection(scale: number): SelectionResult {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return { kind: 'none' }

  const range = selection.getRangeAt(0)
  const page = pageElementOf(range.startContainer)
  if (!page) return { kind: 'none' }
  if (page !== pageElementOf(range.endContainer)) {
    return { kind: 'invalid', reason: 'Select text within a single page to make a note.' }
  }

  const quotedText = selection.toString().trim()
  const rects = clientRectsToPdfRects([...range.getClientRects()], page.getBoundingClientRect(), scale)
  if (!quotedText || rects.length === 0) return { kind: 'none' }
  return { kind: 'anchor', anchor: { page: Number(page.dataset.page), rects, quotedText } }
}
