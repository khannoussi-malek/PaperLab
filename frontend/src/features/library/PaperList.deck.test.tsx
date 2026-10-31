// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'

vi.mock('@/features/triage/pdfCache', () => ({ useCachedPdf: () => ({ doc: null, error: null }), retainOnly: vi.fn(), prefetchPdf: vi.fn() })) // pdfjs needs a worker
vi.mock('@/features/reader/PdfPage', () => ({ PdfPage: () => null }))
vi.mock('../graph/hands/HandsMode', () => ({ default: () => null }))
vi.mock('./PaperPreview', () => ({ PaperPreview: () => <aside>preview</aside> }))
vi.mock('./LibraryDeck', () => ({
  LibraryDeck: ({ papers }: { papers: Paper[] }) => <ol aria-label="deck">{papers.map((p) => <li key={p.id}>{p.title}</li>)}</ol>,
}))
import { PaperList } from './PaperList'

const mk = (id: string, title: string) => ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null }) as unknown as Paper
const papers = [mk('1', 'Alpha cells'), mk('2', 'Beta blockers'), mk('3', 'Alpha waves')]
const selection = { selected: new Set<string>(['2']), onToggle: vi.fn() }
const ui = (view: 'list' | 'deck') => (
  <QueryClientProvider client={new QueryClient()}><PaperList papers={papers} view={view} selection={selection} /></QueryClientProvider>
)

it('deck view keeps the toolbar, passes the visible papers in order, and has no checkboxes or delete', () => {
  render(ui('deck'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'alpha' } })
  expect(screen.getAllByRole('listitem').map((l) => l.textContent)).toEqual(['Alpha cells', 'Alpha waves'])
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull()
})

it('search survives List to Deck to List, and selection with it', () => {
  const view = render(ui('list'))
  expect(screen.getByLabelText('Select Beta blockers')).toBeChecked()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'alpha' } })
  view.rerender(ui('deck'))
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  view.rerender(ui('list'))
  expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('alpha')
  expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  expect(selection.selected.has('2')).toBe(true)
})
