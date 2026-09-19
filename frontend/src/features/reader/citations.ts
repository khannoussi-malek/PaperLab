import type { PageViewport, PDFDocumentProxy } from 'pdfjs-dist'
import { entryAt, pageColumns, type Entry, type EntryAt, type Jump, type PageText, type TextBox } from './citationEntry'
import type { PdfRect } from './coords'

/**
 * D143: the numbered citations a PDF links, read with PDF.js for the whole document each time a paper opens, kept in
 * memory only. PDF.js types only: Vitest hands it a legacy-build document.
 */

/** `AnnotationType.LINK`. A literal: a value import would load PDF.js's browser build into the pure tests. */
const LINK = 2

/** `rect` is the link, `jump` where a click lands; both in the reader's top-left PDF points. */
export type Citation = { id: string; page: number; rect: PdfRect; label: number; entry: Entry | null; jump: Jump }

/** What `getAnnotationsByType` gives for a link (its declared type is `Object`). */
type LinkAnnotation = { id: string; pageIndex: number; rect: number[]; dest?: string | unknown[] | null }
type PageRef = Parameters<PDFDocumentProxy['getPageIndex']>[0]

/** The card's element id, which its citation button's `aria-controls` names. */
export const citationCardId = (citation: Pick<Citation, 'id'>) => `citation-card-${citation.id}`

function toTopLeft(viewport: PageViewport, [x0, y0, x1, y1]: number[]): PdfRect {
  const [ax, ay] = viewport.convertToViewportPoint(x0, y0)
  const [bx, by] = viewport.convertToViewportPoint(x1, y1)
  return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)]
}

/** A page's text as columns of lines, or null past the last page and on a rotated page (skipped, D144). */
async function readPage(doc: PDFDocumentProxy, pageNumber: number): Promise<PageText | null> {
  if (pageNumber > doc.numPages) return null
  const page = await doc.getPage(pageNumber)
  if (page.rotate !== 0) return null
  const viewport = page.getViewport({ scale: 1 })
  const { items } = await page.getTextContent()
  const boxes = items.flatMap((item): TextBox[] => {
    if (!('str' in item)) return []
    const [x0, base] = viewport.convertToViewportPoint(item.transform[4], item.transform[5])
    return [{ str: item.str, x0, x1: x0 + item.width, base, h: item.height || Math.abs(item.transform[3]) }]
  })
  return { page: pageNumber, width: viewport.width, columns: pageColumns(boxes, viewport.width) }
}

/** One pass over a document: each page's text and each distinct destination are read once. */
function passOver(doc: PDFDocumentProxy) {
  const pages = new Map<number, Promise<PageText | null>>()
  const read = (pageNumber: number) => {
    if (!pages.has(pageNumber)) pages.set(pageNumber, readPage(doc, pageNumber))
    return pages.get(pageNumber)!
  }

  async function resolve(dest: string | unknown[]): Promise<EntryAt> {
    const explicit = typeof dest === 'string' ? await doc.getDestination(dest) : dest
    const [ref, , x, y] = explicit ?? []
    if (typeof y !== 'number') return null
    const pageNumber = (typeof ref === 'number' ? ref : await doc.getPageIndex(ref as PageRef)) + 1
    const [here, next] = await Promise.all([read(pageNumber), read(pageNumber + 1)])
    if (!here) return null
    const viewport = (await doc.getPage(pageNumber)).getViewport({ scale: 1 })
    const [vx, vy] = viewport.convertToViewportPoint(typeof x === 'number' ? x : 0, y)
    return entryAt(here, next, { x: typeof x === 'number' && x !== 0 ? vx : null, y: vy })
  }

  const destinations = new Map<string, Promise<EntryAt>>()
  return (dest: string | unknown[]): Promise<EntryAt> => {
    const key = JSON.stringify(dest)
    if (!destinations.has(key)) {
      // One unresolvable destination skips only its own links.
      destinations.set(key, resolve(dest).catch(() => null))
    }
    return destinations.get(key)!
  }
}

async function citationOf(doc: PDFDocumentProxy, link: LinkAnnotation, at: EntryAt): Promise<Citation | null> {
  if (!at) return null
  const viewport = (await doc.getPage(link.pageIndex + 1)).getViewport({ scale: 1 })
  return { id: link.id, page: link.pageIndex + 1, rect: toTopLeft(viewport, link.rect), ...at }
}

/**
 * D143, D144: every link whose destination is a `[N]` reference-list entry, in document order. One unresolvable
 * destination skips only its own links; anything else rejects, and the reader goes on without citations.
 * ponytail: one whole-document pass is 73–139 ms on 12–43 pages. If a very large PDF (a 1,000-page thesis) makes that
 * slow, read per page as pages near the viewport.
 */
export async function readCitations(doc: PDFDocumentProxy): Promise<Citation[]> {
  const resolve = passOver(doc)
  const links = (await doc.getAnnotationsByType(new Set([LINK]), new Set())) as LinkAnnotation[]
  const found = await Promise.all(
    links.filter((link) => link.dest).map(async (link) => citationOf(doc, link, await resolve(link.dest!))),
  )
  return found.filter((citation): citation is Citation => citation !== null)
}

/** The citations of each page, for the reader's per-page hit test and buttons. */
export function citationsByPage(citations: Citation[]): Map<number, Citation[]> {
  const byPage = new Map<number, Citation[]>()
  for (const citation of citations) byPage.set(citation.page, [...(byPage.get(citation.page) ?? []), citation])
  return byPage
}
