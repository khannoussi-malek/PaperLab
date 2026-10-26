// @vitest-environment jsdom
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, PaperMergedError, type Hit, type Paper, type ReferencePage, type SearchRun } from './client'
import {
  PAPERS_POLL_MS,
  embeddingPollInterval,
  isNotesList,
  matchesEligibleHit,
  papersPollInterval,
  queryClient,
  referencePagePollInterval,
  searchRunPollInterval,
  useApplyTag,
  useBulkPatchSearchHits,
  useSetEligibility,
  manuscriptPollInterval,
  useSaveManuscriptFile,
  useWorkspaceMutations,
  useSnowball,
  useUploadHitPdf,
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
describe('workspace rename', () => {
  it('also invalidates the paper-page tag groups, which carry the workspace name', async () => {
    vi.spyOn(api, 'renameWorkspace').mockResolvedValue({} as never)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['papers', 'p1', 'tags'], [])
    const { result } = renderHook(() => useWorkspaceMutations(), { wrapper: withQueryClient(client) })
    result.current.rename.mutate({ id: 'w1', name: 'New' })
    await waitFor(() => expect(result.current.rename.isSuccess).toBe(true))
    expect(client.getQueryState(['papers', 'p1', 'tags'])?.isInvalidated).toBe(true)
  })
})

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

  it('useUploadHitPdf refreshes the hits and papers when the paper already got its PDF elsewhere', async () => {
    vi.spyOn(api, 'uploadHitPdf').mockRejectedValue(new Error('already_has_pdf'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useUploadHitPdf('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ hitId: 'h1', file: new File(['%PDF'], 'p.pdf') })
    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['workspaces'] }))
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['papers'] }))
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

describe('useApplyTag', () => {
  afterEach(() => vi.restoreAllMocks())

  it('invalidates the tag list, the paper-tag map and the per-paper tag groups', async () => {
    vi.spyOn(api, 'applyTag').mockResolvedValue({ tag: 'x', changed: 1, unchanged: 0, skipped: [] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useApplyTag('ws-1'), { wrapper: withQueryClient(client) })
    result.current.mutate({ tag: 'x', paperIds: ['p1'] })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(api.applyTag).toHaveBeenCalledWith('ws-1', 'x', ['p1'])
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['workspaces', 'ws-1', 'tags'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['workspaces', 'ws-1', 'paper-tags'] })
    const perPaper = invalidateSpy.mock.calls.find(([f]) => f?.predicate)?.[0]
    expect(perPaper?.predicate?.({ queryKey: ['papers', 'p1', 'tags'] } as never)).toBe(true)
    expect(perPaper?.predicate?.({ queryKey: ['papers', 'p1', 'notes'] } as never)).toBe(false)
  })
})

describe('a mutation that meets a merged paper', () => {
  afterEach(() => queryClient.clear())

  const failWith = async (error: Error) => {
    queryClient.setQueryData(['papers', 'm1'], paper('ready'))
    queryClient.setQueryData(['papers', 'm1', 'notes'], [])
    const { result } = renderHook(() => useMutation({ mutationFn: () => Promise.reject(error) }), {
      wrapper: withQueryClient(queryClient),
    })
    await result.current.mutateAsync().catch(() => {})
  }

  it('invalidates the open papers, so a reader open on the merged one is sent on at once', async () => {
    await failWith(new PaperMergedError('paper_merged', 'k9'))
    expect(queryClient.getQueryState(['papers', 'm1'])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['papers', 'm1', 'notes'])?.isInvalidated).toBe(false)
  })

  it('leaves them alone on any other error', async () => {
    await failWith(new Error('Server error'))
    expect(queryClient.getQueryState(['papers', 'm1'])?.isInvalidated).toBe(false)
  })
})

describe('manuscript hooks', () => {
  afterEach(() => vi.restoreAllMocks())
  const quiet = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

  it('polls every second while compiling, and stops otherwise or on error', () => {
    expect(manuscriptPollInterval({ compile_status: 'running' }, false)).toBe(1000)
    for (const status of ['never', 'ok', 'failed']) expect(manuscriptPollInterval({ compile_status: status }, false)).toBe(false)
    expect(manuscriptPollInterval(undefined, false)).toBe(false)
    expect(manuscriptPollInterval({ compile_status: 'running' }, true)).toBe(false)
  })

  it('a stale save resolves to a conflict and invalidates nothing', async () => {
    vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('file_changed', 409, { detail: 'file_changed', updated_at: 'T2' }))
    const client = quiet()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useSaveManuscriptFile(), { wrapper: withQueryClient(client) })
    result.current.mutate({ id: 'm', path: 'main.tex', text: 'x', base: 'T1' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ conflict: true, updatedAt: 'T2' })
    expect(spy).not.toHaveBeenCalled()
  })

  it('a good save returns the new updated_at and invalidates the manuscript', async () => {
    vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({ path: 'main.tex', size: 1, updated_at: 'T3' })
    const client = quiet()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useSaveManuscriptFile(), { wrapper: withQueryClient(client) })
    result.current.mutate({ id: 'm', path: 'main.tex', text: 'x', base: null })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ conflict: false, updatedAt: 'T3' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['manuscripts', 'm'] })
  })

  it('any other save error throws', async () => {
    vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('bad_path', 422, { detail: 'bad_path' }))
    const { result } = renderHook(() => useSaveManuscriptFile(), { wrapper: withQueryClient(quiet()) })
    result.current.mutate({ id: 'm', path: '../x', text: 'x', base: null })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(ApiError)
  })

  it('deleting a workspace refreshes the manuscripts', async () => {
    vi.spyOn(api, 'deleteWorkspace').mockResolvedValue(undefined)
    const client = quiet()
    client.setQueryData(['manuscripts', 'list', 'orphans'], [])
    const { result } = renderHook(() => useWorkspaceMutations(), { wrapper: withQueryClient(client) })
    result.current.remove.mutate('w1')
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true))
    expect(client.getQueryState(['manuscripts', 'list', 'orphans'])?.isInvalidated).toBe(true)
  })
})
