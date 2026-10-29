// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'
import { TriageCard } from './TriageCard'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const mk = (extra: Partial<Paper> = {}) =>
  ({ id: 'p1', title: 'Attention', authors: ['Ada Lovelace'], year: 2017, venue: null, abstract: 'An abstract.', status: 'ready',
    has_pdf: true, page_count: 12, is_retracted: false, evidence_access: 'full_text', source_type: null, peer_reviewed: 'unknown',
    published_doi: null, published_venue: null, doi: null, triage: null, reading_pass: 0, ...extra }) as unknown as Paper

function show(paper: Paper, onShowInPdf?: (p: number) => void) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <TriageCard paper={paper} onShowInPdf={onShowInPdf} />
  </QueryClientProvider>)
}
const withSections = (sections: unknown[], chunks: unknown[] = []) => {
  vi.spyOn(api, 'paperSections').mockResolvedValue({ sections, lenses: [] } as never)
  vi.spyOn(api, 'listChunks').mockResolvedValue(chunks as never)
  return vi.spyOn(api, 'triageEvents').mockResolvedValue([])
}
const conclusion = { title: 'Conclusion', role: 'conclusion', chunk_ids: ['c1'], page: 9 }

it('is a group named by its title with byline and page count', () => {
  withSections([])
  show(mk())
  expect(screen.getByRole('group', { name: 'Attention' })).toHaveAttribute('data-triage-card')
  expect(screen.getByText(/Ada Lovelace · 2017/)).toBeInTheDocument()
  expect(screen.getByText(/12 pages/)).toBeInTheDocument()
})

it('shows a long abstract in full in a focusable scroller', () => {
  withSections([])
  const long = 'word '.repeat(600).trim()
  show(mk({ abstract: long }))
  const box = screen.getByLabelText('Abstract')
  expect(box).toHaveAttribute('tabindex', '0')
  expect(box.textContent).toBe(long)
})

it('says No abstract when there is none', () => {
  withSections([])
  show(mk({ abstract: null }))
  expect(screen.getByLabelText('Abstract')).toHaveTextContent('No abstract')
})

it('flags a retracted paper and shows source badges', () => {
  withSections([])
  show(mk({ is_retracted: true }))
  expect(screen.getByText('This paper has been retracted')).toBeInTheDocument()
  expect(screen.getByText('Full text')).toBeInTheDocument()
})

it('shows the chip and the history line of a decided paper', async () => {
  withSections([]).mockResolvedValue([{ id: 'e', created_at: '2026-10-01T09:05:00', source: 'desk', pile: 'skim', before_pass: 0, after_pass: 1, before_triage: null, after_triage: 'keep' }] as never)
  show(mk({ triage: 'keep', reading_pass: 1 }))
  expect(await screen.findByText(/1 Oct, 09:05/)).toBeInTheDocument()
  expect(screen.getByTestId('triage-chip')).toBeInTheDocument()
})

it('makes no events request for an undecided paper', () => {
  const events = withSections([])
  show(mk())
  expect(events).not.toHaveBeenCalled()
})

it('shows the conclusion with its page', async () => {
  withSections([conclusion], [{ id: 'c1', text: 'We conclude it works.', ordinal: 0, page: 9 }])
  show(mk())
  expect(await screen.findByText('Conclusion · p. 9')).toBeInTheDocument()
  expect(screen.getByText('We conclude it works.')).toBeInTheDocument()
})

it('shows nothing for a paper with neither section', async () => {
  const spy = withSections([{ title: 'Intro', role: 'intro', chunk_ids: ['i'], page: 1 }])
  show(mk())
  await waitFor(() => expect(spy).toBeDefined())
  await new Promise((r) => setTimeout(r, 20))
  expect(screen.queryByText(/Conclusion|Discussion|isn't ready/)).toBeNull()
})

it("says full text isn't ready for a PDF with no sections, but nothing without a PDF", async () => {
  withSections([])
  show(mk())
  expect(await screen.findByText("Full text isn't ready yet")).toBeInTheDocument()
  cleanup()
  show(mk({ has_pdf: false }))
  await new Promise((r) => setTimeout(r, 20))
  expect(screen.queryByText(/isn't ready/)).toBeNull()
})

it('shows a quiet placeholder while loading and a one-line notice on error', async () => {
  vi.spyOn(api, 'paperSections').mockRejectedValue(new Error('boom'))
  show(mk())
  expect(screen.getByTestId('conclusion-loading')).toBeInTheDocument()
  expect(await screen.findByText(/Couldn't load the conclusion/)).toBeInTheDocument()
})

it('has no Show in PDF button unless asked, and passes the page when it is', async () => {
  withSections([conclusion], [{ id: 'c1', text: 'Done.', ordinal: 0, page: 9 }])
  const onShow = vi.fn()
  show(mk())
  await screen.findByText('Done.')
  expect(screen.queryByRole('button', { name: /Show in PDF/ })).toBeNull()
  cleanup()
  show(mk(), onShow)
  ;(await screen.findByRole('button', { name: /Show in PDF/ })).click()
  expect(onShow).toHaveBeenCalledWith(9)
})

it('sits in the light paper scope in both themes', () => {
  withSections([])
  show(mk())
  expect(screen.getByRole('group', { name: 'Attention' })).toHaveClass('paper-surface')
})
