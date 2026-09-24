// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { HitTable } from './HitTable'
import { api, type Hit } from '@/api/client'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const baseHit = {
  id: 'h1',
  run_id: 'run-1',
  external_ref_id: null,
  source_method: 'arxiv',
  normalized_title: 'a paper about llms',
  first_seen_at: '2026-09-24T00:00:00Z',
  stage1_status: null,
  stage1_exclude_reason: null,
  stage1_note: null,
  priority: null,
  topic_fit: null,
  acquisition_status: 'pending',
  paper_id: null,
} satisfies Hit

beforeEach(() => {
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [baseHit], next_cursor: null })
  vi.spyOn(api, 'patchSearchHit').mockResolvedValue(baseHit)
  vi.spyOn(api, 'importSearchHits')
  // jsdom never lays anything out, so offsetHeight is always 0 — the virtualizer treats a zero-height
  // scroll container as "nothing visible" and renders no rows at all. Give it a plausible viewport.
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(600)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(600)
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders hit titles from the paginated query', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  expect(await screen.findByText('a paper about llms')).toBeInTheDocument()
})

test('clicking a row opens the review drawer', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  fireEvent.click(await screen.findByRole('button', { name: /a paper about llms/ }))

  expect(screen.getByRole('dialog', { name: 'Review hit' })).toBeInTheDocument()
})

test('marking not relevant without picking a reason does not submit', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  fireEvent.click(await screen.findByRole('button', { name: /a paper about llms/ }))

  fireEvent.click(screen.getByRole('button', { name: 'Not relevant' }))

  expect(api.patchSearchHit).not.toHaveBeenCalled()
})

test('picking a reason then marking not relevant sends the exclude reason', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  fireEvent.click(await screen.findByRole('button', { name: /a paper about llms/ }))

  fireEvent.change(screen.getByLabelText('Exclusion reason'), { target: { value: 'duplicate' } })
  fireEvent.click(screen.getByRole('button', { name: 'Not relevant' }))

  await waitFor(() =>
    expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', {
      stage1_status: 'not_relevant',
      stage1_exclude_reason: 'duplicate',
    }),
  )
})

test('marking relevant sends only stage1_status', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  fireEvent.click(await screen.findByRole('button', { name: /a paper about llms/ }))

  fireEvent.click(screen.getByRole('button', { name: 'Relevant' }))

  await waitFor(() => expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', { stage1_status: 'relevant' }))
})
