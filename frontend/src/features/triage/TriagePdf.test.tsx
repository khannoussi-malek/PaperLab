// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'

vi.mock('../reader/PdfPage', () => ({ PdfPage: ({ pageNumber, scale }: { pageNumber: number; scale: number }) => <i data-page={pageNumber} data-scale={scale}>{pageNumber}</i> }))
const doc = { numPages: 3, getPage: async () => ({ getViewport: () => ({ width: 612, height: 792 }) }) }
vi.mock('./pdfCache', () => ({ useCachedPdf: (url: string | null) => ({ doc: url ? doc : null, error: null }) }))

import { TriagePdf } from './TriagePdf'

let now = 1000
beforeAll(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }) })
beforeEach(() => { now = 1000; vi.spyOn(performance, 'now').mockImplementation(() => now) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const rect = (top: number) => ({ top, bottom: top + 100, left: 0, right: 100, width: 100, height: 100, x: 0, y: top, toJSON: () => ({}) }) as DOMRect
/** Pages 100 px tall stacked from the scroller's top, shifted by the scroll offset. */
function fakeLayout(box: HTMLElement) {
  Object.defineProperty(box, 'clientHeight', { value: 300, configurable: true })
  box.getBoundingClientRect = () => rect(0)
  box.querySelectorAll<HTMLElement>('[data-page]').forEach((p) => {
    p.getBoundingClientRect = () => rect((Number(p.dataset.page) - 1) * 100 + 40 - box.scrollTop)
  })
}
async function setup(extra: Partial<Parameters<typeof TriagePdf>[0]> = {}) {
  const onInteract = vi.fn()
  const onPage = vi.fn()
  render(<TriagePdf paperId="p1" active target={null} onInteract={onInteract} onPage={onPage} {...extra} />)
  const box = await screen.findByLabelText('PDF pages')
  await screen.findByText(/of 3/)
  fakeLayout(box)
  return { onInteract, onPage, box }
}

it('is a PDF region with a toolbar and every page', async () => {
  await setup()
  const region = screen.getByRole('region', { name: 'PDF' })
  expect(region).toHaveAttribute('data-triage-pdf')
  expect(region).toHaveAttribute('data-triage-region')
  expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  expect(document.querySelectorAll('[data-page]')).toHaveLength(3)
})

it('shows nothing and asks for nothing when not active', () => {
  render(<TriagePdf paperId="p1" active={false} target={null} onInteract={vi.fn()} />)
  expect(screen.queryByLabelText('PDF pages')).toBeNull()
})

it('a wheel then a scroll is an interaction; a bare scroll is not', async () => {
  const { box, onInteract } = await setup()
  fireEvent.scroll(box)
  expect(onInteract).not.toHaveBeenCalled()
  fireEvent.wheel(box)
  fireEvent.scroll(box)
  expect(onInteract).toHaveBeenCalledTimes(1)
})

it('a zoom (button or key) and a page key are interactions', async () => {
  const { box, onInteract, onPage } = await setup()
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
  expect(onInteract).toHaveBeenCalledTimes(1)
  fireEvent.keyDown(box, { key: '-' })
  expect(onInteract).toHaveBeenCalledTimes(2)
  fireEvent.keyDown(box, { key: ']' })
  expect(onInteract).toHaveBeenCalledTimes(3)
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  expect(onPage).toHaveBeenLastCalledWith(2, 3)
  expect(box.scrollTop).toBe(140) // page 2 starts 140 px down: its top lands at the scroller top
})

it('zoom scales every page from the fit width', async () => {
  const { box } = await setup()
  const scale = () => Number(document.querySelector('[data-scale]')!.getAttribute('data-scale'))
  const before = scale()
  fireEvent.keyDown(box, { key: '+' })
  expect(scale()).toBeGreaterThan(before)
  fireEvent.keyDown(box, { key: '0' })
  expect(scale()).toBe(before)
})

it('PDF keys act only with the scroller focused', async () => {
  const { onInteract } = await setup()
  fireEvent.keyDown(screen.getByRole('button', { name: 'Next page' }), { key: ']' })
  fireEvent.keyDown(screen.getByRole('region', { name: 'PDF' }), { key: '+' })
  expect(onInteract).not.toHaveBeenCalled()
})

it('a selection inside the column counts, one outside does not', async () => {
  const { onInteract } = await setup()
  const text = document.querySelector('[data-page]')!.firstChild
  const pick = (anchorNode: Node | null) => {
    vi.spyOn(window, 'getSelection').mockReturnValue({ isCollapsed: false, anchorNode } as Selection)
    document.dispatchEvent(new Event('selectionchange'))
  }
  pick(document.body)
  expect(onInteract).not.toHaveBeenCalled()
  pick(text)
  expect(onInteract).toHaveBeenCalledTimes(1)
})

it('the page counter follows the scroll', async () => {
  const { box, onInteract } = await setup()
  box.scrollTop = 150
  fireEvent.scroll(box)
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  box.scrollTop = 0
  fireEvent.scroll(box)
  expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  expect(onInteract).not.toHaveBeenCalled() // no input, so not the reader's doing
})

it('a target places its page and counts as the user asking for it', async () => {
  const onInteract = vi.fn()
  const { rerender } = render(<TriagePdf paperId="p1" active target={null} onInteract={onInteract} />)
  const box = await screen.findByLabelText('PDF pages')
  await screen.findByText(/of 3/)
  fakeLayout(box)
  rerender(<TriagePdf paperId="p1" active target={{ page: 3, n: 1 }} onInteract={onInteract} />)
  expect(box.scrollTop).toBeGreaterThan(0)
  expect(onInteract).toHaveBeenCalledTimes(1)
})

it('a paper whose document is still loading says so quietly', () => {
  render(<TriagePdf paperId="p1" active target={null} onInteract={vi.fn()} />)
  expect(screen.getByLabelText('PDF pages')).toBeInTheDocument()
})
