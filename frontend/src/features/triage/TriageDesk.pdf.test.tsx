// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'

vi.mock('../reader/PdfPage', () => ({ PdfPage: ({ pageNumber }: { pageNumber: number }) => <i>{pageNumber}</i> }))
vi.mock('../library/GetPdfActions', () => ({ GetPdfActions: () => <button>Get PDF actions</button> }))
vi.mock('./pdfCache', () => ({
  useCachedPdf: (url: string | null) => ({ doc: url ? { numPages: 2, getPage: async () => ({ getViewport: () => ({ width: 612, height: 792 }) }) } : null, error: null }),
  retainOnly: vi.fn(),
  prefetchPdf: vi.fn(),
}))
import { TriageDesk } from './TriageDesk'

let decide: ReturnType<typeof vi.spyOn>
beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
beforeEach(() => {
  window.innerWidth = 1400
  decide = vi.spyOn(api, 'decideTriage').mockResolvedValue({ event: { id: 'e' } } as never)
  vi.spyOn(api, 'paperSections').mockReturnValue(new Promise(() => {}) as never)
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks() })

const mk = (id: string, extra: Partial<Paper> = {}) =>
  ({ id, title: `Paper ${id}`, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z`, ...extra }) as unknown as Paper
function setup(papers = [mk('1'), mk('2')]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={papers} library={papers} scope="library" sourceLabel="your library" filterKey="" onExit={vi.fn()} onShowKept={vi.fn()} />
    </QueryClientProvider>,
  )
  return screen.getByRole('group', { name: 'Triage' })
}
const column = () => screen.queryByRole('region', { name: 'PDF' })
const sent = () => (decide.mock.calls[0][1] as { pdf_opened: boolean; pdf_ms: number; card_ms: number })

it('shows the column by default beside the card, and P hides and shows it, remembered', async () => {
  const root = setup()
  expect(await screen.findByRole('region', { name: 'PDF' })).toBeInTheDocument()
  fireEvent.keyDown(root, { key: 'p' })
  expect(column()).toBeNull()
  expect(localStorage.getItem('paperlab-triage-pdf')).toBe('0')
  fireEvent.keyDown(root, { key: 'p' })
  expect(column()).not.toBeNull()
  expect(localStorage.getItem('paperlab-triage-pdf')).toBe('1')
})

it('opens hidden when it was left hidden; unusable storage is fine', () => {
  localStorage.setItem('paperlab-triage-pdf', '0')
  setup()
  expect(column()).toBeNull()
  cleanup()
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('no') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('no') })
  const root = setup()
  expect(column()).not.toBeNull()
  fireEvent.keyDown(root, { key: 'p' })
  expect(column()).toBeNull()
})

it('a card whose column was only visible decides with pdf_opened false', async () => {
  const root = setup()
  await screen.findByRole('region', { name: 'PDF' })
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalled())
  expect(sent().pdf_opened).toBe(false)
})

it('an interaction in the column makes the decision say pdf_opened true; the next card starts fresh', async () => {
  const root = setup()
  const box = await screen.findByLabelText('PDF pages')
  fireEvent.keyDown(box, { key: '+' })
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(1))
  expect(sent().pdf_opened).toBe(true)
  fireEvent.keyDown(root, { key: '2' })
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  expect((decide.mock.calls[1][1] as { pdf_opened: boolean }).pdf_opened).toBe(false)
})

it('pile keys from inside the column do not decide', async () => {
  setup()
  const box = await screen.findByLabelText('PDF pages')
  fireEvent.keyDown(box, { key: '1' })
  fireEvent.keyDown(box, { key: 'ArrowRight' })
  fireEvent.keyDown(box, { key: ' ' })
  expect(decide).not.toHaveBeenCalled()
})

it('a paper without a PDF has no column, says so, offers Get PDF, and still decides', async () => {
  const root = setup([mk('1', { has_pdf: false }), mk('2')])
  expect(column()).toBeNull()
  expect(screen.getByText('No PDF for this paper.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Get PDF actions' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /PDF \(P\)/ })).toBeDisabled()
  act(() => { fireEvent.keyDown(root, { key: '2' }) })
  await waitFor(() => expect(decide).toHaveBeenCalled())
  expect(sent().pdf_opened).toBe(false)
})
