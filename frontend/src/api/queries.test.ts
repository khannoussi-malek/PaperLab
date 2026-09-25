// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type Hit, type Paper, type SearchRun } from './client'
import {
  PAPERS_POLL_MS,
  embeddingPollInterval,
  matchesEligibleHit,
  papersPollInterval,
  searchRunPollInterval,
  useSetEligibility,
  useSnowball,
} from './queries'

const prismaRootKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'prisma']
const searchHitsAllKey = (workspaceId: string) => ['workspaces', workspaceId, 'search', 'hits', 'all', 'all']

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

// Controller ruling (Task 10): PrismaTab stays mounted forever (WorkspacePage's forceMount), so its
// usePrismaExport query never refetches on its own once data changes underneath it. These prove the fix
// targets only the small prisma cache — never `searchHitsRoot`'s multi-thousand-row unfiltered pool, which is
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

  it('useSnowball invalidates only the prisma root, never searchHitsRoot wholesale', async () => {
    vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 2, skipped_seeds: [], errors: {} })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useSnowball('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ seed_paper_ids: ['p1'], backward: true, forward: true })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(invalidateSpy).toHaveBeenCalledTimes(1)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: prismaRootKey('ws-1') })
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
})

describe('embeddingPollInterval', () => {
  it('asks again every 2 s while search is being rebuilt, and stops once it is done or before the first load', () => {
    expect(embeddingPollInterval({ rebuild: { done: 3, total: 20 } })).toBe(PAPERS_POLL_MS)
    expect(PAPERS_POLL_MS).toBe(2000)
    expect(embeddingPollInterval({ rebuild: null })).toBe(false)
    expect(embeddingPollInterval(undefined)).toBe(false)
  })
})
