// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ScreeningTab } from './ScreeningTab'
import * as queries from '@/api/queries'
import { api } from '@/api/client'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const importedHit = {
  id: 'h1',
  run_id: 'run-1',
  external_ref_id: 'ref-1',
  source_method: 'arxiv',
  normalized_title: 'imported paper lowercase',
  first_seen_at: '2026-09-24T00:00:00Z',
  stage1_status: 'relevant',
  stage1_exclude_reason: null,
  stage1_note: null,
  priority: null,
  topic_fit: null,
  acquisition_status: 'imported',
  paper_id: 'p1',
  title: 'Imported Paper',
  stage2_status: null,
  stage2_exclude_reason: null,
}

const manualHit = {
  ...importedHit,
  id: 'h2',
  run_id: 'run-2',
  paper_id: 'p2',
  acquisition_status: 'manual',
  title: 'Manually Uploaded Paper',
  normalized_title: 'manual paper lowercase',
}

// Mirrors ManualAcquisitionTab.test.tsx's idiom, but ScreeningTab calls useSearchHits twice (once per
// acquisition_status: 'imported' and 'manual') and merges the results, so the mock dispatches on that arg.
function mockHits(byStatus: Record<string, object[]>) {
  vi.spyOn(queries, 'useSearchHits').mockImplementation(
    (_workspaceId: string, _stage1Status?: string, acquisitionStatus?: string) =>
      ({
        data: { pages: [{ items: byStatus[acquisitionStatus ?? ''] ?? [], next_cursor: null }] },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
      }) as any,
  )
}

beforeEach(() => {
  mockHits({ imported: [importedHit], manual: [] })
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows an imported hit with Include/Exclude actions and no verdict yet', () => {
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', undefined, 'imported')
  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', undefined, 'manual')
  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Include' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Exclude' })).toBeInTheDocument()
  expect(screen.getByText('not assessed')).toBeInTheDocument()
})

test('merges imported and manual hits from the two separate useSearchHits calls', () => {
  mockHits({ imported: [importedHit], manual: [manualHit] })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
  expect(screen.getByText('Manually Uploaded Paper')).toBeInTheDocument()
})

test("clicking Include calls setEligibility with status 'include' and the hit's own paper/run id", async () => {
  const setEligibilitySpy = vi.spyOn(api, 'setEligibility').mockResolvedValue({
    paper_id: 'p1', search_run_id: 'run-1', stage2_status: 'include', stage2_exclude_reason: null, assessed_at: '2026-09-24T00:00:00Z',
  })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Include' }))

  await waitFor(() =>
    expect(setEligibilitySpy).toHaveBeenCalledWith('ws-1', 'p1', 'run-1', { status: 'include' }),
  )
})

test('Exclude opens a free-text reason input, gated by disabled until text is entered', async () => {
  const setEligibilitySpy = vi.spyOn(api, 'setEligibility').mockResolvedValue({
    paper_id: 'p1', search_run_id: 'run-1', stage2_status: 'exclude', stage2_exclude_reason: 'off topic', assessed_at: '2026-09-24T00:00:00Z',
  })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Exclude' }))

  // No fixed-enum <select> like stage-1's EXCLUDE_REASONS — a real free-text input instead.
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  const input = screen.getByLabelText(/Exclusion reason/i)
  const confirm = screen.getByRole('button', { name: 'Confirm exclude' })
  expect(confirm).toBeDisabled()

  fireEvent.change(input, { target: { value: 'off topic' } })
  expect(confirm).not.toBeDisabled()
  fireEvent.click(confirm)

  await waitFor(() =>
    expect(setEligibilitySpy).toHaveBeenCalledWith('ws-1', 'p1', 'run-1', {
      status: 'exclude',
      exclude_reason: 'off topic',
    }),
  )
})

test("renders a Snowball control per hit that calls useSnowball with that hit's paper_id as the seed", async () => {
  const snowballSpy = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Snowball' }))

  await waitFor(() =>
    expect(snowballSpy).toHaveBeenCalledWith('ws-1', { seed_paper_ids: ['p1'], backward: true, forward: true }),
  )
})

test('a successful snowball with new hits surfaces the count', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 3, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Snowball' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Found 3 new papers')
})

test('a successful snowball with zero new hits says so, not nothing', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Snowball' }))

  expect(await screen.findByRole('status')).toHaveTextContent('No new papers found')
})

test('a snowball with skipped seeds mentions them in the status message', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: ['p1'], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Snowball' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Skipped 1')
})

test('a failed snowball request shows an alert with the error', async () => {
  vi.spyOn(api, 'snowball').mockRejectedValue(new Error('Semantic Scholar is off.'))

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Snowball' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Semantic Scholar is off.')
})

test('a failed eligibility update shows an alert with the error', async () => {
  vi.spyOn(api, 'setEligibility').mockRejectedValue(new Error('Could not save eligibility.'))

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Include' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not save eligibility.')
})

test('shows an empty-state message when there is nothing to screen', () => {
  mockHits({ imported: [], manual: [] })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByText(/nothing to screen/i)).toBeInTheDocument()
})
