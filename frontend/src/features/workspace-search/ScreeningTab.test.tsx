// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ScreeningTab } from './ScreeningTab'
import * as queries from '@/api/queries'
import { api } from '@/api/client'
import { readerHref, workspaceHref } from '@/lib/route'

// jsdom lacks these; Radix Select needs them.
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false

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

type HitsMock = {
  items: object[]
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  fetchNextPage?: () => void
  isPending?: boolean
  isError?: boolean
  error?: Error
  refetch?: () => void
}

// Mirrors ManualAcquisitionTab.test.tsx's idiom, but ScreeningTab calls useSearchHits twice (once per
// acquisition_status: 'imported' and 'manual') and merges the results, so the mock dispatches on that arg.
// Each status also carries its own pagination fields (hasNextPage/fetchNextPage/isFetchingNextPage), since each
// useSearchHits call paginates independently.
function mockHits(byStatus: Record<string, HitsMock>) {
  vi.spyOn(queries, 'useSearchHits').mockImplementation(
    (_workspaceId: string, _stage1Status?: string, acquisitionStatus?: string) => {
      const entry = byStatus[acquisitionStatus ?? ''] ?? { items: [] }
      return {
        data: { pages: [{ items: entry.items, next_cursor: null }] },
        hasNextPage: entry.hasNextPage ?? false,
        isFetchingNextPage: entry.isFetchingNextPage ?? false,
        fetchNextPage: entry.fetchNextPage ?? vi.fn(),
        isPending: entry.isPending ?? false,
        isError: entry.isError ?? false,
        error: entry.error ?? null,
        refetch: entry.refetch ?? vi.fn(),
      } as any
    },
  )
}

beforeEach(() => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] } })
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows an imported hit with Include/Exclude actions and no verdict yet', () => {
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', 'relevant', 'imported')
  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', 'relevant', 'manual')
  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Include' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Exclude' })).toBeInTheDocument()
  expect(screen.getByText('Not assessed')).toBeInTheDocument()
})

test('merges imported and manual hits from the two separate useSearchHits calls', () => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [manualHit] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
  expect(screen.getByText('Manually Uploaded Paper')).toBeInTheDocument()
})

test('the filter box narrows the already-loaded rows by title, client-side', () => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [manualHit] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search results to screen'), { target: { value: 'manually' } })

  expect(screen.queryByText('Imported Paper')).not.toBeInTheDocument()
  expect(screen.getByText('Manually Uploaded Paper')).toBeInTheDocument()
  expect(screen.getByText('1 of 2')).toBeInTheDocument()
})

test('a filter matching nothing shows a "no match" message instead of an empty list', () => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search results to screen'), { target: { value: 'nothing matches this' } })

  expect(screen.getByText(/No results match/)).toBeInTheDocument()
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

async function pickReason(name: string) {
  fireEvent.keyDown(screen.getByRole('combobox', { name: /Exclusion reason/i }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name }))
}

test('exclude with a listed reason saves its label', async () => {
  const setEligibilitySpy = vi.spyOn(api, 'setEligibility').mockResolvedValue({
    paper_id: 'p1', search_run_id: 'run-1', stage2_status: 'exclude', stage2_exclude_reason: 'Duplicate', assessed_at: '2026-09-24T00:00:00Z',
  })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Exclude' }))

  const confirm = screen.getByRole('button', { name: 'Confirm exclude' })
  expect(confirm).toBeDisabled()
  await pickReason('Duplicate')
  expect(confirm).not.toBeDisabled()
  fireEvent.click(confirm)

  await waitFor(() =>
    expect(setEligibilitySpy).toHaveBeenCalledWith('ws-1', 'p1', 'run-1', { status: 'exclude', exclude_reason: 'Duplicate' }),
  )
})

test('exclude with Other saves the typed reason', async () => {
  const setEligibilitySpy = vi.spyOn(api, 'setEligibility').mockResolvedValue({
    paper_id: 'p1', search_run_id: 'run-1', stage2_status: 'exclude', stage2_exclude_reason: 'off topic', assessed_at: '2026-09-24T00:00:00Z',
  })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Exclude' }))
  await pickReason('Other (type a reason)')

  const confirm = screen.getByRole('button', { name: 'Confirm exclude' })
  expect(confirm).toBeDisabled()
  fireEvent.change(screen.getByPlaceholderText('Reason for excluding…'), { target: { value: 'off topic' } })
  expect(confirm).not.toBeDisabled()
  fireEvent.click(confirm)

  await waitFor(() =>
    expect(setEligibilitySpy).toHaveBeenCalledWith('ws-1', 'p1', 'run-1', { status: 'exclude', exclude_reason: 'off topic' }),
  )
})

test("a review row's title opens the paper", () => {
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByRole('link', { name: 'Imported Paper' })).toHaveAttribute('href', readerHref('p1'))
})

test("renders a Snowball control per hit that calls useSnowball with that hit's paper_id as the seed", async () => {
  const snowballSpy = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))

  await waitFor(() =>
    expect(snowballSpy).toHaveBeenCalledWith('ws-1', { seed_paper_ids: ['p1'], backward: true, forward: true }),
  )
})

test('a successful snowball with new hits surfaces the count', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 3, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Found 3 new papers')
})

test('a successful snowball with zero new hits says so, not nothing', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))

  expect(await screen.findByRole('status')).toHaveTextContent('No new papers found')
})

test('a snowball with skipped seeds mentions them in the status message', async () => {
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: ['p1'], errors: {} })

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Skipped 1')
})

test('a failed snowball request shows an alert with the error', async () => {
  vi.spyOn(api, 'snowball').mockRejectedValue(new Error('Semantic Scholar is off.'))

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Semantic Scholar is off.')
})

test('a failed eligibility update shows an alert with the error', async () => {
  vi.spyOn(api, 'setEligibility').mockRejectedValue(new Error('Could not save eligibility.'))

  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Include' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not save eligibility.')
})

test('shows an empty-state message when there is nothing to screen', () => {
  mockHits({ imported: { items: [] }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByRole('heading', { name: 'Nothing to review yet' })).toBeInTheDocument()
  expect(screen.getByText('Import relevant results with a PDF first.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' })).toHaveAttribute('href', workspaceHref('ws-1', 'search'))
})

test('the empty-state link keeps the active run', () => {
  mockHits({ imported: { items: [] }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" runId="r1" />)
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' })).toHaveAttribute('href', workspaceHref('ws-1', 'search', 'r1'))
})

test('shows included and excluded rows in words', () => {
  mockHits({ imported: { items: [{ ...importedHit, stage2_status: 'include' }] }, manual: { items: [{ ...manualHit, stage2_status: 'exclude' }] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByText('Included')).toBeInTheDocument()
  expect(screen.getByText('Excluded')).toBeInTheDocument()
})

test('hides Load more controls when neither status has a next page (the common case)', () => {
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
})

test('a Load more control for imported hits fetches that query\'s next page, not the other one', () => {
  const importedFetchNextPage = vi.fn()
  const manualFetchNextPage = vi.fn()
  mockHits({
    imported: { items: [importedHit], hasNextPage: true, fetchNextPage: importedFetchNextPage },
    manual: { items: [manualHit], fetchNextPage: manualFetchNextPage },
  })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  fireEvent.click(screen.getByRole('button', { name: 'Load more imported' }))

  expect(importedFetchNextPage).toHaveBeenCalledTimes(1)
  expect(manualFetchNextPage).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Load more manual' })).not.toBeInTheDocument()
})

test('a Load more control for manual hits fetches that query\'s next page, not the other one', () => {
  const importedFetchNextPage = vi.fn()
  const manualFetchNextPage = vi.fn()
  mockHits({
    imported: { items: [importedHit], fetchNextPage: importedFetchNextPage },
    manual: { items: [manualHit], hasNextPage: true, fetchNextPage: manualFetchNextPage },
  })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  fireEvent.click(screen.getByRole('button', { name: 'Load more manual' }))

  expect(manualFetchNextPage).toHaveBeenCalledTimes(1)
  expect(importedFetchNextPage).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Load more imported' })).not.toBeInTheDocument()
})

test('Load more imported is disabled and relabelled while that page is already fetching', () => {
  mockHits({ imported: { items: [importedHit], hasNextPage: true, isFetchingNextPage: true }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()
})

test('a hit with no linked paper record (paper_id null) renders no actions, not a crash or a malformed mutation call', () => {
  mockHits({ imported: { items: [{ ...importedHit, id: 'h3', paper_id: null }] }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
  expect(screen.getByText('No linked paper record')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Include' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Exclude' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Find citing & cited papers' })).not.toBeInTheDocument()
})

test('while loading it shows a skeleton, not the empty copy', () => {
  vi.spyOn(queries, 'useSearchHits').mockReturnValue({ data: undefined, isPending: true, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() } as any)
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('Nothing to review yet')).not.toBeInTheDocument()
})

test('a failed query shows the error and Retry, not the empty copy', () => {
  const refetch = vi.fn()
  vi.spyOn(queries, 'useSearchHits').mockReturnValue({ data: undefined, isPending: false, isError: true, error: new Error('Nope.'), refetch, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() } as any)
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getAllByRole('button', { name: 'Retry' })[0])
  expect(refetch).toHaveBeenCalled()
  expect(screen.queryByText('Nothing to review yet')).not.toBeInTheDocument()
})

test('rows from one query show while the other is still loading', () => {
  vi.spyOn(queries, 'useSearchHits').mockImplementation(
    (_w: string, _s?: string, acquisition?: string) =>
      (acquisition === 'imported'
        ? { data: { pages: [{ items: [importedHit], next_cursor: null }] }, isPending: false, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }
        : { data: undefined, isPending: true, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }) as any,
  )
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByText('Imported Paper')).toBeInTheDocument()
})

test('one query empty and the other pending shows the skeleton, not the empty copy', () => {
  vi.spyOn(queries, 'useSearchHits').mockImplementation(
    (_w: string, _s?: string, acquisition?: string) =>
      (acquisition === 'imported'
        ? { data: { pages: [{ items: [], next_cursor: null }] }, isPending: false, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }
        : { data: undefined, isPending: true, hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }) as any,
  )
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('Nothing to review yet')).not.toBeInTheDocument()
})

test('Find citing & cited papers replaces Snowball, with an explained term beside it', () => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.queryByText('Snowball')).toBeNull()
  expect(screen.getByRole('button', { name: 'What does finding citing & cited papers do?' })).toBeInTheDocument()
})

test('the row wraps its actions and offers the renamed stage-2 reasons', async () => {
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  const row = screen.getByRole('button', { name: 'Exclude' }).parentElement!
  expect(row.className).toContain('flex-wrap')
  fireEvent.click(screen.getByRole('button', { name: 'Exclude' }))
  fireEvent.keyDown(screen.getByRole('combobox', { name: /Exclusion reason/i }), { key: 'Enter' })
  const options = (await screen.findAllByRole('option')).map((o) => o.textContent)
  expect(options).toEqual(['Wrong topic', 'Wrong study type', 'Wrong population', 'Not peer-reviewed', 'Duplicate', 'Other (type a reason)'])
})

test('a paper saved without a PDF is a blocked row: No PDF yet, needs the full text, Upload PDF, no verdict buttons', () => {
  const awaiting = { ...importedHit, id: 'h7', paper_id: 'p7', acquisition_status: 'awaiting_pdf', title: 'Abstract Only Paper' }
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] }, awaiting_pdf: { items: [awaiting] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)

  expect(screen.getByText('Abstract Only Paper')).toBeInTheDocument()
  expect(screen.getByText('No PDF yet')).toBeInTheDocument()
  expect(screen.getByText('Needs the full text to assess')).toBeInTheDocument()
  expect(screen.getByLabelText('Upload PDF for Abstract Only Paper')).toBeInTheDocument()
  // only the imported row has verdict buttons
  expect(screen.getAllByRole('button', { name: 'Include' })).toHaveLength(1)
  expect(screen.getAllByRole('button', { name: 'Exclude' })).toHaveLength(1)
  expect(screen.getByText('1 to screen')).toBeInTheDocument()
})

test('a needs_full_text refusal reads in words', async () => {
  vi.spyOn(api, 'setEligibility').mockRejectedValue(new Error('needs_full_text'))
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Include' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Needs the full text to assess.')
})

const awaitingRow = { ...importedHit, id: 'h7', paper_id: 'p7', acquisition_status: 'awaiting_pdf', title: 'Abstract Only Paper' }

test('a blocked row never shows a verdict label', () => {
  mockHits({ imported: { items: [] }, manual: { items: [] }, awaiting_pdf: { items: [{ ...awaitingRow, stage2_status: 'include' }] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByText('Needs the full text to assess')).toBeInTheDocument()
  expect(screen.queryByText('Included')).toBeNull()
})

test('the filtered count leaves blocked rows out, like the unfiltered one', () => {
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] }, awaiting_pdf: { items: [awaitingRow] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  fireEvent.change(screen.getByLabelText('Search results to screen'), { target: { value: 'paper' } })
  expect(screen.getByText('1 of 1')).toBeInTheDocument()
})

test('a failed awaiting query shows the load error with a retry, not a silent drop', () => {
  const refetch = vi.fn()
  mockHits({ imported: { items: [importedHit] }, manual: { items: [] }, awaiting_pdf: { items: [], isError: true, error: new Error('Awaiting broke.'), refetch } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.getByText('Awaiting broke.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
})

test('while the awaiting query loads it does not claim there is nothing to review', () => {
  mockHits({ imported: { items: [] }, manual: { items: [] }, awaiting_pdf: { items: [], isPending: true } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(screen.queryByText('Nothing to review yet')).toBeNull()
})

test('the awaiting hits come from the one query step 2 and the counts share (no stage-1 filter), kept to relevant here', () => {
  const spy = vi.spyOn(queries, 'useSearchHits')
  mockHits({ imported: { items: [] }, manual: { items: [] }, awaiting_pdf: { items: [awaitingRow, { ...awaitingRow, id: 'h8', paper_id: 'p8', title: 'Not Relevant One', stage1_status: 'not_relevant' }] } })
  renderWithClient(<ScreeningTab workspaceId="ws-1" />)
  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', undefined, 'awaiting_pdf')
  expect(screen.getByText('Abstract Only Paper')).toBeInTheDocument()
  expect(screen.queryByText('Not Relevant One')).toBeNull()
  void spy
})
