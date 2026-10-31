// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'

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
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear() })

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
