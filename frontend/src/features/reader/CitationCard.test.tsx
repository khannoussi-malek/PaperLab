// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { Reference, References } from '@/api/client'
import { CitationCard } from './CitationCard'
import type { Citation } from './citations'

const firstPage = vi.hoisted(() => vi.fn(() => null))
vi.mock('@/features/library/FirstPage', () => ({ FirstPage: firstPage })) // the real one loads the PDF
vi.mock('./citationMatch', async (actual) => ({
  ...(await actual<typeof import('./citationMatch')>()),
  cardView: (_: Citation, { data }: { data: References }) => ({ kind: 'in-library', reference: data.rows[0] }),
}))

const reference = (over: Partial<Reference>) =>
  ({
    id: 'r1', title: 'Held paper', authors: [], year: null, venue: null, doi: null, arxiv_id: null, openalex_id: null,
    s2_id: null, cited_by_count: null, has_pdf: false, cocitation: 0, paper_id: 'p9', paper_has_pdf: true, position: 0,
    queued_at: null, ...over,
  }) as Reference

const renderCard = (ref: Reference) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CitationCard
        citation={{ label: '1' } as unknown as Citation}
        references={{ data: { rows: [ref] } as unknown as References, isError: false }}
        style={{}}
        onPointerEnter={vi.fn()}
        onPointerLeave={vi.fn()}
        onOpenReferences={vi.fn()}
      />
    </QueryClientProvider>,
  )

test('a cited library paper without a PDF shows no first page, says No PDF yet, and still opens', () => {
  renderCard(reference({ paper_has_pdf: false }))
  expect(firstPage).not.toHaveBeenCalled()
  expect(screen.getByText('No PDF yet')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open in PaperLab' })).toHaveAttribute('href', '#/papers/p9')
})

test('a cited library paper with a PDF shows its first page', () => {
  renderCard(reference({}))
  expect(firstPage).toHaveBeenCalled()
  expect(screen.queryByText('No PDF yet')).toBeNull()
})
