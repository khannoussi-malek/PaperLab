// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, test, vi } from 'vitest'
import { NoFreePdfError, api } from '@/api/client'
import type { Paper } from '@/api/client'
import { PaperPreview as Preview } from './PaperPreview'

const qc = new QueryClient()
const PaperPreview = (props: { paper: Paper }) => (
  <QueryClientProvider client={qc}>
    <Preview {...props} />
  </QueryClientProvider>
)

const firstPage = vi.hoisted(() => vi.fn(() => null))
vi.mock('./FirstPage', () => ({ FirstPage: firstPage })) // the real one loads the PDF

const paper = (over: Partial<Paper>) =>
  ({
    id: 'p1', title: 'Sleep and memory', authors: ['Ada Lee'], year: 2020, venue: 'Sleep', page_count: null,
    status: 'ready', status_error: null, doi: null, abstract: 'Sleep helps memory.', created_at: '2026-10-18T10:00:00Z',
    has_pdf: true, details_source: null, field_sources: {}, ...over,
  }) as Paper

test('a paper without a PDF shows no first page: it says so, and leads with the abstract', () => {
  render(<PaperPreview paper={paper({ has_pdf: false, details_source: 'crossref' })} />)
  expect(firstPage).not.toHaveBeenCalled()
  expect(screen.getByText('No PDF yet')).toBeInTheDocument()
  expect(screen.getByText('Details from Crossref')).toBeInTheDocument()
  expect(screen.getByText('Sleep helps memory.')).toBeInTheDocument()
  expect(screen.queryByText(/Processing/)).toBeNull()
})

test('a ready paper with a PDF still shows its first page', () => {
  render(<PaperPreview paper={paper({})} />)
  expect(firstPage).toHaveBeenCalled()
  expect(screen.queryByText('No PDF yet')).toBeNull()
})

test('a paper without a PDF offers Upload PDF and Find free copy', () => {
  render(<PaperPreview paper={paper({ has_pdf: false })} />)
  expect(screen.getByLabelText('Upload PDF for Sleep and memory')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Find free copy for Sleep and memory' })).toBeInTheDocument()
})

test("a failed find for one paper does not show under the next paper previewed", async () => {
  vi.spyOn(api, 'findPaperPdf').mockRejectedValue(new NoFreePdfError('x', [{ url: 'https://a.example/A.pdf', outcome: 'http_403' }], []))
  const a = paper({ id: 'pa', title: 'Paper A', has_pdf: false })
  const b = paper({ id: 'pb', title: 'Paper B', has_pdf: false })
  const view = render(<PaperPreview paper={a} />)
  fireEvent.click(screen.getByRole('button', { name: 'Find free copy for Paper A' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('A.pdf')
  view.rerender(<PaperPreview paper={b} />)
  expect(screen.queryByRole('alert')).toBeNull()
})
