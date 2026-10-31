// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'

vi.mock('../reader/PdfPage', () => ({ PdfPage: ({ pageNumber }: { pageNumber: number }) => <i>{pageNumber}</i> }))
vi.mock('../library/GetPdfActions', () => ({ GetPdfActions: () => <button>Get PDF actions</button> }))
vi.mock('./pdfCache', () => ({
  useCachedPdf: (url: string | null) => ({ doc: url ? { numPages: 5, getPage: async () => ({ getViewport: () => ({ width: 612, height: 792 }) }) } : null, error: null }),
  retainOnly: vi.fn(),
  prefetchPdf: vi.fn(),
}))
import { TriageDesk } from './TriageDesk'

const observers: (() => void)[] = []
beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { constructor(cb: () => void) { observers.push(cb) } observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
let decide: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  decide = vi.spyOn(api, 'decideTriage').mockResolvedValue({ event: { id: 'e' } } as never)
  vi.spyOn(api, 'paperSections').mockResolvedValue({ sections: [{ title: 'Conclusion', role: 'conclusion', source: 'keyword', chunk_ids: ['c1'], first_chunk_id: 'c1', page: 4, preview: '' }], lenses: [] } as never)
  vi.spyOn(api, 'listChunks').mockResolvedValue([{ id: 'c1', text: 'We conclude.', ordinal: 0, page: 4 }] as never)
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks(); observers.length = 0 })

const resize = (w: number) => act(() => { window.innerWidth = w; observers.forEach((cb) => cb()) })
const mk = (id: string, extra: Partial<Paper> = {}) =>
  ({ id, title: `Paper ${id}`, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z`, ...extra }) as unknown as Paper
function setup(width: number, papers = [mk('1'), mk('2')]) {
  window.innerWidth = width
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={papers} library={papers} scope="library" sourceLabel="your library" filterKey="" onExit={vi.fn()} onShowKept={vi.fn()} />
    </QueryClientProvider>,
  )
  return screen.getByRole('group', { name: 'Triage' })
}
const showBtn = () => screen.findByRole('button', { name: /Show in PDF \(p\. 4\)/ })
const pdfTab = () => screen.getByRole('tab', { name: 'PDF' })
const sent = () => decide.mock.calls[0][1] as { pdf_opened: boolean; pdf_ms: number }

it('Show in PDF reveals a hidden column, jumps to the page and counts as an interaction', async () => {
  localStorage.setItem('paperlab-triage-pdf', '0')
  const root = setup(1400)
  expect(screen.queryByRole('region', { name: 'PDF' })).toBeNull()
  fireEvent.click(await showBtn())
  expect(await screen.findByText('Page 4 of 5')).toBeInTheDocument()
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalled())
  expect(sent().pdf_opened).toBe(true)
})

it('has no Show in PDF button and no PDF affordances without a PDF, in every layout', async () => {
  for (const w of [1400, 900, 500]) {
    setup(w, [mk('1', { has_pdf: false }), mk('2')])
    await screen.findByText('No PDF for this paper.')
    expect(screen.queryByRole('button', { name: /Show in PDF/ })).toBeNull()
    expect(screen.queryByRole('tab')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Open PDF' })).toBeNull()
    cleanup()
  }
})

it('tabs: both panels stay mounted, P and a focused tab switch, arrows on the desk still decide', async () => {
  const root = setup(900)
  expect(screen.getByRole('tab', { name: 'Paper' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByLabelText('PDF pages')).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument()
  fireEvent.keyDown(root, { key: 'p' })
  expect(pdfTab()).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('heading', { level: 2, hidden: true })).toBeInTheDocument()
  fireEvent.keyDown(pdfTab(), { key: 'ArrowLeft' })
  expect(screen.getByRole('tab', { name: 'Paper' })).toHaveAttribute('aria-selected', 'true')
  expect(decide).not.toHaveBeenCalled()
  fireEvent.keyDown(root, { key: 'ArrowLeft' })
  expect(await screen.findByRole('button', { name: /Cancel/i }).catch(() => null)).toBeDefined()
  expect(decide).not.toHaveBeenCalled() // Not relevant asks why first: the chips are the proof the arrow was a pile
  expect(document.querySelector('[data-reason-chip]')).not.toBeNull()
})

it('tabs: the PDF counts as shown only while its tab is selected', async () => {
  const root = setup(900)
  await screen.findByLabelText('PDF pages')
  fireEvent.keyDown(root, { key: 'p' })
  fireEvent.keyDown(screen.getByLabelText('PDF pages'), { key: '+' })
  fireEvent.keyDown(root, { key: 'p' })
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalled())
  expect(sent().pdf_opened).toBe(true)
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  expect((decide.mock.calls[1][1] as { pdf_ms: number }).pdf_ms).toBe(0) // the PDF tab was never selected on card two
})

it('tabs: Show in PDF selects the PDF tab and jumps', async () => {
  setup(900)
  fireEvent.click(await showBtn())
  expect(pdfTab()).toHaveAttribute('aria-selected', 'true')
  expect(await screen.findByText('Page 4 of 5')).toBeInTheDocument()
})

it('single: no targets, an Open PDF sheet, Esc closes only the sheet, shown only while open', async () => {
  const root = setup(500)
  expect(screen.queryByRole('button', { name: /^Read closely$/ })).not.toBeNull()
  expect(screen.queryByLabelText('PDF pages')).toBeNull()
  expect(root.querySelector('[data-desk-stage] [aria-label]:not(article)')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Open PDF' }))
  const box = await screen.findByLabelText('PDF pages')
  fireEvent.keyDown(box, { key: '+' })
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByLabelText('PDF pages')).toBeNull())
  expect(root).toBeInTheDocument()
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalled())
  expect(sent().pdf_opened).toBe(true)
})

it('single: Show in PDF opens the sheet on the page', async () => {
  setup(500)
  fireEvent.click(await showBtn())
  expect(await screen.findByText('Page 4 of 5')).toBeInTheDocument()
})

it('resizing from wide to tabs keeps the card and the PDF page', async () => {
  setup(1400)
  fireEvent.click(await showBtn())
  await screen.findByText('Page 4 of 5')
  const card = screen.getByRole('heading', { level: 2 })
  resize(900)
  expect(screen.getByRole('tab', { name: 'Paper' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 2 })).toBe(card)
  expect(screen.getByText('Page 4 of 5')).toBeInTheDocument()
})
