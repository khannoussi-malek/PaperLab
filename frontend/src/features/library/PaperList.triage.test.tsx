// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'

vi.mock('@/features/triage/pdfCache', () => ({ useCachedPdf: () => ({ doc: null, error: null }), retainOnly: vi.fn(), prefetchPdf: vi.fn() })) // pdfjs needs a worker
vi.mock('@/features/reader/PdfPage', () => ({ PdfPage: () => null }))
vi.mock('../graph/hands/HandsMode', () => ({ default: () => null }))
vi.mock('./PaperPreview', () => ({ PaperPreview: () => <aside>preview</aside> }))
import { PaperList } from './PaperList'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
let decide: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  let n = 0
  decide = vi.spyOn(api, 'decideTriage').mockImplementation((async () => ({ event: { id: `e${++n}` } })) as never)
  vi.spyOn(api, 'undoTriage').mockResolvedValue({} as never)
  vi.spyOn(api, 'paperSections').mockReturnValue(new Promise(() => {}) as never)
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks() })

const mk = (id: string, title: string, extra: Partial<Paper> = {}) =>
  ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z`, ...extra }) as unknown as Paper
const papers = [mk('1', 'Alpha cells'), mk('2', 'Beta blockers'), mk('3', 'Alpha waves')]
const ui = (view: 'list' | 'triage', list = papers, onExit = vi.fn()) => (
  <QueryClientProvider client={new QueryClient()}>
    <PaperList papers={list} view={view} selection={{ selected: new Set(), onToggle: vi.fn() }} triageScope="library" sourceLabel="your library" onTriageExit={onExit} />
  </QueryClientProvider>
)
const desk = () => screen.getByRole('group', { name: 'Triage' })

it('shows the desk with only the searched papers, no checkboxes or delete', () => {
  render(ui('triage'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beta' } })
  expect(within(desk()).getByText(/1 left of 1/)).toBeInTheDocument()
  expect(within(desk()).getByRole('heading', { name: 'Beta blockers' })).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull()
})

it('keeps the search across List, Triage and List, and typing re-freezes the stack', () => {
  const view = render(ui('list'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'alpha' } })
  view.rerender(ui('triage'))
  expect(within(desk()).getByText(/2 left of 2/)).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'waves' } })
  expect(within(desk()).getByText(/1 left of 1/)).toBeInTheDocument()
  view.rerender(ui('list'))
  expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('waves')
})

it('the full library, not the filtered list, serves the card', () => {
  render(ui('triage'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beta' } })
  expect(screen.getByRole('heading', { name: 'Beta blockers' })).toBeInTheDocument()
})

const type = (value: string) => fireEvent.change(screen.getByRole('searchbox'), { target: { value } })
const left = () => within(desk()).getByRole('progressbar').getAttribute('aria-valuenow')

it('a search with no match keeps the desk, its session and its undo; clearing brings the stack back', async () => {
  render(ui('triage'))
  fireEvent.keyDown(desk(), { key: '1' }) // Alpha cells, Read closely
  expect(left()).toBe('1')
  type('zzzz')
  expect(desk()).toBeInTheDocument()
  expect(screen.getByText('No paper in this view matches your search.')).toBeInTheDocument()
  fireEvent.click(within(desk()).getByRole('button', { name: 'Clear search' }))
  expect(screen.queryByText('No paper in this view matches your search.')).toBeNull()
  expect(left()).toBe('1')
  expect(screen.getByRole('button', { name: /Undo: Read closely/ })).toBeInTheDocument()
  fireEvent.keyDown(desk(), { key: 'u' })
  expect(left()).toBe('0')
})

it('typing in the search never moves focus to the desk and never decides', () => {
  render(ui('triage'))
  const box = screen.getByRole('searchbox')
  box.focus()
  type('zz'); type('zz2'); type('')
  fireEvent.keyDown(box, { key: ' ' })
  fireEvent.keyDown(box, { key: '2' })
  expect(box).toHaveFocus()
  expect(decide).not.toHaveBeenCalled()
  expect(left()).toBe('0')
})

it('a desk opened while the search box is focused leaves focus there', () => {
  const view = render(ui('list'))
  screen.getByRole('searchbox').focus()
  view.rerender(ui('triage'))
  expect(screen.getByRole('searchbox')).toHaveFocus()
})

it('Show kept papers in the list sets the Reading filter to Keep and shows the list', () => {
  const onShowKept = vi.fn()
  const list = [mk('1', 'Alpha cells', { triage: 'keep' }), mk('2', 'Beta blockers')]
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaperList papers={list} view="triage" triageScope="library" sourceLabel="your library" onShowKept={onShowKept} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByLabelText('Include decided papers'))
  fireEvent.keyDown(desk(), { key: '1' })
  fireEvent.keyDown(desk(), { key: '1' })
  fireEvent.click(screen.getByRole('button', { name: 'Show kept papers in the list' }))
  expect(onShowKept).toHaveBeenCalled()
  expect(screen.getByRole('combobox', { name: 'Reading' })).toHaveTextContent('Keep')
})
