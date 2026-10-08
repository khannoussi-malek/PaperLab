// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type Hit, type Paper, type ReferencePage, type SearchRun } from './client'
import {
  PAPERS_POLL_MS,
  embeddingPollInterval,
  isNotesList,
  matchesEligibleHit,
  papersPollInterval,
  referencePagePollInterval,
  searchRunPollInterval,
  useBulkPatchSearchHits,
  useSetEligibility,
  useSnowball,
} from './queries'

const prismaRootKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'prisma']
const readingQueueRootKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'reading-queue']
const searchHitsAllKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'hits', 'all', 'all']
const rankedHitsKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'ranked']

function withQueryClient(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
}

const paper = (status: string) => ({ status }) as Paper
const run = (status: string) => ({ status }) as SearchRun
const hit = (paperId: string | null, runId: string) => ({ paper_id: paperId, run_id: runId }) as Hit

describe('papersPollInterval', () => {
  it('polls while any paper is still ingesting', () => {
    expect(papersPollInterval([paper('ready'), paper('extracting')])).toBe(PAPERS_POLL_MS)
  })

  it('stops once every paper is ready or failed, or before the first load', () => {
    expect(papersPollInterval([paper('ready'), paper('failed')])).toBe(false)
    expect(papersPollInterval(undefined)).toBe(false)
  })
})

describe('searchRunPollInterval', () => {
  it('polls while the run is still running', () => {
    expect(searchRunPollInterval(run('running'))).toBe(PAPERS_POLL_MS)
  })

  it('stops once the run is no longer running, or before the first load', () => {
    expect(searchRunPollInterval(run('exhausted'))).toBe(false)
    expect(searchRunPollInterval(undefined)).toBe(false)
  })
})

describe('matchesEligibleHit', () => {
  it('matches a hit whose paper_id and run_id both match the eligibility response', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-1', 'run-1')).toBe(true)
  })

  it('does not match on run_id alone (same paper, different run)', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-1', 'run-2')).toBe(false)
  })

  it('does not match on paper_id alone (same run, different paper)', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-2', 'run-1')).toBe(false)
  })

  it('never matches a hit with no imported paper (paper_id null)', () => {
    expect(matchesEligibleHit(hit(null, 'run-1'), 'paper-1', 'run-1')).toBe(false)
  })
})

// Controller ruling (Task 10, extended by the reading-bridge fix round): PrismaTab and ReadingQueueTab both stay
// mounted forever (WorkspacePage's forceMount), so their own queries never refetch on their own once data changes
// underneath them. These prove the fix targets only those small caches — never `searchHitsRoot`'s multi-thousand-row
// unfiltered pool, which is
// the exact request-storm `patchMatchingHits`'s own docstring warns against re-triggering wholesale.
describe('prisma cache invalidation', () => {
  afterEach(() => vi.restoreAllMocks())

  it('useSetEligibility (routed through patchMatchingHits) invalidates the prisma root', async () => {
    vi.spyOn(api, 'setEligibility').mockResolvedValue({
      paper_id: 'p1',
      search_run_id: 'run-1',
      stage2_status: 'include',
      stage2_exclude_reason: null,
      assessed_at: '2026-09-24T00:00:00Z',
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useSetEligibility('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ paperId: 'p1', runId: 'run-1', body: { status: 'include' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: prismaRootKey('ws-1') }))
  })

  it('useSnowball invalidates only the prisma and reading-queue roots, never searchHitsRoot wholesale', async () => {
    vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 2, skipped_seeds: [], errors: {} })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useSnowball('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ seed_paper_ids: ['p1'], backward: true, forward: true })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(invalidateSpy).toHaveBeenCalledTimes(2)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: prismaRootKey('ws-1') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: readingQueueRootKey('ws-1') })
  })

  // Task 3: snowballed hits were invisible in the Search tab until an unrelated refetch or a full page reload —
  // nothing marked the unfiltered pool's own query stale. The fix must reset (not invalidate) exactly that one
  // query, and only when there's something new to show.
  it('useSnowball resets only the unfiltered hit pool (exact match) when new_hits > 0', async () => {
    vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 2, skipped_seeds: [], errors: {} })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const resetSpy = vi.spyOn(client, 'resetQueries')

    const { result } = renderHook(() => useSnowball('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ seed_paper_ids: ['p1'], backward: true, forward: true })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(resetSpy).toHaveBeenCalledTimes(1)
    expect(resetSpy).toHaveBeenCalledWith({ queryKey: searchHitsAllKey('ws-1'), exact: true })
  })

  it('useSnowball does not reset the hit pool when new_hits is 0', async () => {
    vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const resetSpy = vi.spyOn(client, 'resetQueries')

    const { result } = renderHook(() => useSnowball('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ seed_paper_ids: ['p1'], backward: true, forward: true })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(resetSpy).not.toHaveBeenCalled()
  })

  // HitTable's multi-select action bar: bulk_review_hits' response carries no ids back, but the mutation already
  // knows every hit_id it sent, so useBulkPatchSearchHits patches them directly instead of refetching the pool.
  it('useBulkPatchSearchHits patches every selected hit in the cached pool, leaving others untouched', async () => {
    vi.spyOn(api, 'bulkPatchSearchHits').mockResolvedValue({ updated: 2 })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const row = (id: string) => ({ ...hit(null, 'run-1'), id, stage1_status: null })
    client.setQueryData(searchHitsAllKey('ws-1'), {
      pages: [{ items: [row('h1'), row('h2'), row('h3')], next_cursor: null }],
      pageParams: [undefined],
    })

    const { result } = renderHook(() => useBulkPatchSearchHits('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ hit_ids: ['h1', 'h2'], stage1_status: 'relevant' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const items = (client.getQueryData(searchHitsAllKey('ws-1')) as { pages: { items: Hit[] }[] }).pages[0].items
    expect(items.find((h) => h.id === 'h1')?.stage1_status).toBe('relevant')
    expect(items.find((h) => h.id === 'h2')?.stage1_status).toBe('relevant')
    expect(items.find((h) => h.id === 'h3')?.stage1_status).toBeNull()
  })

  it('useBulkPatchSearchHits invalidates ranked hits, the prisma root, and the reading queue root', async () => {
    vi.spyOn(api, 'bulkPatchSearchHits').mockResolvedValue({ updated: 2 })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useBulkPatchSearchHits('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ hit_ids: ['h1'], stage1_status: 'relevant' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: rankedHitsKey('ws-1') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: prismaRootKey('ws-1') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: readingQueueRootKey('ws-1') })
  })
})

describe('embeddingPollInterval', () => {
  it('asks again every 2 s while search is being rebuilt, and stops once it is done or before the first load', () => {
    expect(embeddingPollInterval({ rebuild: { done: 3, total: 20 } })).toBe(PAPERS_POLL_MS)
    expect(PAPERS_POLL_MS).toBe(2000)
    expect(embeddingPollInterval({ rebuild: null })).toBe(false)
    expect(embeddingPollInterval(undefined)).toBe(false)
  })
})

describe('isNotesList', () => {
  it('is true for a paper’s notes, its chat history, and for every workspace query, whose Notes tabs and counts list notes', () => {
    expect(isNotesList(['papers', 'p1', 'notes'])).toBe(true)
    expect(isNotesList(['papers', 'p1', 'chat'])).toBe(true)
    expect(isNotesList(['workspaces'])).toBe(true)
    expect(isNotesList(['workspaces', 'w1', 'notes'])).toBe(true)
  })

  it('is false for a paper or its chunks', () => {
    expect(isNotesList(['papers', 'p1'])).toBe(false)
    expect(isNotesList(['papers', 'p1', 'chunks', 2])).toBe(false)
  })

  it('is true for the Notes page’s lists', () => {
    expect(isNotesList(['notes', 'all'])).toBe(true)
    expect(isNotesList(['notes', 'none'])).toBe(true)
  })
})

describe('referencePagePollInterval', () => {
  const page = (state: string) => ({ coverage: { unfetched: [{ state }] } }) as ReferencePage

  it('polls only while an unfetched paper is fetching', () => {
    expect(referencePagePollInterval(page('fetching'))).toBe(PAPERS_POLL_MS)
    expect(referencePagePollInterval(page('none'))).toBe(false)
    expect(referencePagePollInterval(undefined)).toBe(false)
  })
})

describe('useReadingContext', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches and returns reading context for a paper', async () => {
    vi.spyOn(api, 'readingContext').mockResolvedValue({ contexts: [] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    // Import the hook inside the test to fail if it's not defined
    const { useReadingContext } = await import('./queries')

    const { result } = renderHook(() => useReadingContext('paper-1'), { wrapper: withQueryClient(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ contexts: [] })
  })
})

describe('useReadingQueue', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches and returns reading queue for a run', async () => {
    vi.spyOn(api, 'readingQueue').mockResolvedValue({ rows: [] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { useReadingQueue } = await import('./queries')

    const { result } = renderHook(() => useReadingQueue('ws-1', 'run-1'), { wrapper: withQueryClient(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ rows: [] })
  })

  it('is disabled when runId is null', async () => {
    vi.spyOn(api, 'readingQueue').mockResolvedValue({ rows: [] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { useReadingQueue } = await import('./queries')

    const { result } = renderHook(() => useReadingQueue('ws-1', null), { wrapper: withQueryClient(client) })

    // Query should not fire when runId is null
    expect(result.current.data).toBeUndefined()
    expect(vi.mocked(api.readingQueue)).not.toHaveBeenCalled()
  })
})
