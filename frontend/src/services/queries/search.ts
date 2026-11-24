import { QueryClient, useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/services/api'
import type { BranchIn, BulkHitReviewUpdate, EligibilityUpdate, Hit, HitListOut, HitReviewUpdate, SavedSearch, SavedSearchCreate, SavedSearchInbox, SavedSearchUpdate, ScreeningState, ScreeningUpdate, SearchRun, SearchRunCreate, SearchRunSummary, SnowballRequest } from '@/entities'
import { keys, PAPERS_POLL_MS } from './core'

/** Poll a search run only while it's still running. */
export function searchRunPollInterval(run: SearchRun | undefined): number | false {
  return run?.status === 'running' ? PAPERS_POLL_MS : false
}

/** Starts a search run for a workspace's saved query. */
export function useStartSearchRun(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SearchRunCreate) => api.startSearchRun(workspaceId, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
  })
}

/** Polls only while one of its runs is going, so "N new" moves when a scheduled run finds something. */
export const useSavedSearches = (workspaceId: string) =>
  useQuery({
    queryKey: keys.savedSearches(workspaceId),
    queryFn: () => api.listSavedSearches(workspaceId),
    refetchInterval: (query) =>
      query.state.data?.some((s: SavedSearch) => s.last_run_status === 'running') ? PAPERS_POLL_MS : false,
  })

function useSavedSearchMutation<V, R>(workspaceId: string, mutationFn: (variables: V) => Promise<R>, alsoRuns = false) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.savedSearches(workspaceId) }),
        ...(alsoRuns ? [client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) })] : []),
      ]),
  })
}

export const useCreateSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (body: SavedSearchCreate) => api.createSavedSearch(workspaceId, body))
export const useUpdateSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (v: { id: string; body: SavedSearchUpdate }) =>
    api.updateSavedSearch(workspaceId, v.id, v.body))
export const useDeleteSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.deleteSavedSearch(workspaceId, id))
/** Resolves with the new run, so the caller can switch the Search tab to it. */
export const useRunSavedSearchNow = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.runSavedSearchNow(workspaceId, id), true)

/** The reader opened a saved search's new finds: its "N new" count starts again from now. */
export const useMarkSavedSearchSeen = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.markSavedSearchSeen(workspaceId, id))

/** Stops a running search run. `stop_run` 409s ("search_run_not_running") when the run already finished naturally
 * right as the user clicked Stop — a harmless race (Minor 5), not a real error, so it's swallowed here: the mutation
 * re-fetches the run's real (now-finished) state and resolves with that instead of surfacing `.isError`. */
export function useStopSearchRun(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) => {
      try {
        return await api.stopSearchRun(workspaceId, runId)
      } catch (error) {
        if (error instanceof Error && error.message === 'search_run_not_running') {
          return api.getSearchRun(workspaceId, runId)
        }
        throw error
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
  })
}

/** Continues a stopped, cut-short or paused run from where each source stopped; the run goes back to running. */
export function useContinueSearchRun(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => api.continueSearchRun(workspaceId, runId),
    onSuccess: (_run, runId) =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.searchRun(workspaceId, runId) }),
      ]),
  })
}

/** One search run; polls while it's still running. `runId` is null before a run has started. */
export const useSearchRun = (workspaceId: string, runId: string | null) =>
  useQuery({
    queryKey: keys.searchRun(workspaceId, runId ?? ''),
    queryFn: () => api.getSearchRun(workspaceId, runId!),
    enabled: runId !== null,
    refetchInterval: (query) => searchRunPollInterval(query.state.data),
  })

/** How every paper reached the workspace: the snowball tree's nodes, links, roots and per-level counts. */
export const useProvenance = (workspaceId: string) =>
  useQuery({ queryKey: keys.provenance(workspaceId), queryFn: () => api.provenance(workspaceId) })

/** Every root-to-hit path for one node; only fetched once a node is picked. */
export const usePaths = (workspaceId: string, hitId: string | null) =>
  useQuery({
    queryKey: [...keys.provenance(workspaceId), 'paths', hitId],
    queryFn: () => api.hitPaths(workspaceId, hitId!),
    enabled: hitId !== null,
  })

/** One hit for the tree's side panel. Nested under the provenance key so every tree refresh re-reads it. */
export const useSearchHit = (workspaceId: string, hitId: string | null) =>
  useQuery({
    queryKey: [...keys.provenance(workspaceId), 'hit', hitId],
    queryFn: () => api.getSearchHit(workspaceId, hitId!),
    enabled: hitId !== null,
  })

/** What a branch or snowball change touches: the tree, the Snowball next list and the runs list. */
export const refreshTree = (client: QueryClient, workspaceId: string) =>
  Promise.all([
    client.invalidateQueries({ queryKey: keys.provenance(workspaceId) }),
    client.invalidateQueries({ queryKey: keys.snowballNext(workspaceId) }),
    client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
  ])

/** Go further / Stop here / Undecided for one hit or hand-added paper. */
export function useSetBranch(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: BranchIn) => api.setBranch(workspaceId, body),
    onSuccess: () => refreshTree(client, workspaceId),
  })
}

/** "Summarise now": the AI reads one hit against the review question. Overwrites its suggestion; the tree re-reads it. */
export function useSuggestHit(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, confirmRemote }: { hitId: string; confirmRemote?: boolean }) => api.suggestHit(workspaceId, hitId, confirmRemote),
    onSuccess: () => refreshTree(client, workspaceId),
  })
}

/** Go-further branches with a direction not snowballed yet. */
export const useSnowballNext = (workspaceId: string) =>
  useQuery({ queryKey: keys.snowballNext(workspaceId), queryFn: () => api.snowballNext(workspaceId) })

/** "Run all" on the Snowball next list: one request, a snowball per direction group on the server. */
export function useRunSnowballNext(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.runSnowballNext(workspaceId),
    onSuccess: (result) =>
      Promise.all([
        refreshTree(client, workspaceId),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
        result.new_hits > 0
          ? client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true })
          : undefined,
      ]),
  })
}

/** The workspace's recent runs, newest first; polls only while one is still running. */
export const useSearchRuns = (workspaceId: string) =>
  useQuery({
    queryKey: keys.searchRuns(workspaceId),
    queryFn: () => api.listSearchRuns(workspaceId),
    refetchInterval: (query) =>
      query.state.data?.some((r: SearchRunSummary) => r.status === 'running') ? PAPERS_POLL_MS : false,
  })

/** A run's hits, keyset-paginated; `stage1Status`/`acquisitionStatus` each filter to one status ('all' when omitted). */
export const useSearchHits = (
  workspaceId: string,
  stage1Status?: string,
  acquisitionStatus?: string,
  /** `sort: 'ai'` orders by the AI score (cursor is then an offset); `minRelevance` keeps scores at or above it. */
  /** `inbox` narrows to what one saved search found after `since` (M7.6). */
  options: { sort?: 'ai'; minRelevance?: number; inbox?: SavedSearchInbox } = {},
) =>
  useInfiniteQuery({
    // The default key stays exactly the plain pool's (other code resets it by exact key); only AI/filtered views add a suffix.
    queryKey: [
      ...keys.searchHits(workspaceId, stage1Status ?? 'all', acquisitionStatus ?? 'all'),
      ...(options.sort || options.minRelevance ? [options.sort ?? 'found', options.minRelevance ?? 0] : []),
      ...(options.inbox ? ['inbox', options.inbox.savedSearchId, options.inbox.since] : []),
    ],
    queryFn: ({ pageParam }) =>
      api.listSearchHits(workspaceId, {
        after: pageParam, limit: 50, stage1_status: stage1Status, acquisition_status: acquisitionStatus,
        sort: options.sort, min_relevance: options.minRelevance,
        saved_search_id: options.inbox?.savedSearchId, found_after: options.inbox?.since,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })

/** Unscreened hits, most likely relevant first (M31a); refetched after every decision, since each one retrains it. */
export const useRankedHits = (workspaceId: string, enabled: boolean, inbox?: SavedSearchInbox) =>
  useQuery({
    queryKey: [...keys.rankedHits(workspaceId), ...(inbox ? ['inbox', inbox.savedSearchId, inbox.since] : [])],
    queryFn: () =>
      api.rankedSearchHits(
        workspaceId, 200, inbox && { saved_search_id: inbox.savedSearchId, found_after: inbox.since },
      ),
    enabled,
  })

/** The workspace's screening criteria and suggestion-job state (M31b). Polls only while a suggestion job is
 * running or stopping; the hit pool itself refreshes separately once the job goes back to idle. */
export const useScreeningState = (workspaceId: string) =>
  useQuery({
    queryKey: keys.screening(workspaceId),
    queryFn: () => api.screeningState(workspaceId),
    refetchInterval: (query) => (query.state.data?.suggest_status === 'idle' ? false : 2000),
  })

function useScreeningMutation<T>(workspaceId: string, fn: (arg: T) => Promise<ScreeningState>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (state) => {
      client.setQueryData(keys.screening(workspaceId), state)
      client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) })
      client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) })
    },
  })
}

export const useSaveScreening = (workspaceId: string) =>
  useScreeningMutation(workspaceId, (body: ScreeningUpdate) => api.saveScreening(workspaceId, body))
export const useStartSuggestions = (workspaceId: string) =>
  useScreeningMutation(workspaceId, (confirmRemote: boolean) => api.startSuggestions(workspaceId, confirmRemote))
export const useStopSuggestions = (workspaceId: string) =>
  useScreeningMutation(workspaceId, () => api.stopSuggestions(workspaceId))

/** Every source's raw, pre-dedup count of what it's found so far, summed (`run.stats_json.per_source_raw_count`)
 * — "how many papers we found," before removing the ones more than one source turned up. `undefined` before the
 * run has reported any progress yet. */
export function totalRawFound(run: SearchRun | undefined): number | undefined {
  const rawCounts = run?.stats_json?.per_source_raw_count as Record<string, number> | undefined
  return rawCounts ? Object.values(rawCounts).reduce((sum, count) => sum + count, 0) : undefined
}

/** Signals that the hit pool is worth refreshing, without refreshing it automatically.
 *
 * An earlier version auto-invalidated the pool on every bit of progress (I1). That doesn't scale: invalidating
 * an infinite query re-fetches every already-loaded page, not just new data, and a search run can find a pool of
 * 3,000+ hits spread across dozens of pages — re-fetching all of them, repeatedly, in the background while a real
 * run trickles in new results over many minutes froze the UI (observed: 70+ requests in a single burst, every
 * ~20s, for as long as the run kept running). There is no cheap way to fetch only the new tail with this query
 * library's infinite-query model, so the fix is to not do it automatically at all — surface a lightweight count
 * (from the already-polled `stats_json`, no extra request) and let an explicit user action (`acknowledge`) pay
 * the one-time cost of a real refresh, exactly once, on demand.
 *
 * Keyed off the *cumulative* `stats_json.per_source_raw_count` (summed across sources, via `totalRawFound`), not
 * `last_batch_new_hits` — the worker overwrites `last_batch_new_hits` fresh every batch
 * (workers/workspace_search.py), so it's "how many hits did *this* batch add," not a running total, and two
 * different batches can report the same count. */
export function useNewHitsAvailable(run: SearchRun | undefined) {
  const rawCountTotal = totalRawFound(run)
  const baseline = useRef<number | undefined>(undefined)
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    if (rawCountTotal === undefined) return
    if (baseline.current === undefined) {
      baseline.current = rawCountTotal // first tick just sets the starting point — nothing "new" relative to it yet
      return
    }
    if (rawCountTotal > baseline.current) setAvailable(true)
  }, [rawCountTotal])

  return {
    available,
    acknowledge: () => {
      baseline.current = rawCountTotal
      setAvailable(false)
    },
  }
}

/** The one-time, explicit refresh `useNewHitsAvailable`'s banner triggers on click. */
export function useRefreshHits(workspaceId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) })
}

/** After one hit's fields change (review, import, upload), refresh every cached view of the hit pool:
 *
 * - Patch the new fields directly into every already-loaded page, in place, with no network request. This is
 *   what keeps HitTable's own view correct — it holds the *unfiltered* pool, which can run into the thousands of
 *   hits across dozens of pages, and re-fetching all of them on every single review/import/upload is the same
 *   scaling problem `useNewHitsAvailable`'s docstring describes for background polling (observed: a full-pool
 *   refetch burst on every click).
 * - Actually re-fetch any *filtered* view (e.g. ManualAcquisitionTab's `acquisition_status: 'failed'` list, which
 *   `WorkspacePage` keeps mounted alongside HitTable via `forceMount`): changing a hit's status can push it in or
 *   out of a filter's membership, which patching its fields in place can't fix — but a filtered view is always a
 *   small, bounded subset of the pool, so a real refetch there is cheap.
 * - Also invalidate `prismaRoot`: review/import/upload/eligibility can all shift the PRISMA funnel's counts, and
 *   PrismaTab stays mounted forever (`WorkspacePage`'s `forceMount`), so its export query never refetches on its
 *   own without this. `prismaRoot`'s pool is tiny (a handful of runs), unlike `searchHitsRoot` above, so a
 *   wholesale invalidate here needs no predicate.
 * - Also invalidate `readingQueueRoot`, same reasoning: an import can add a paper to the reading queue, and an
 *   eligibility change can add/remove one from it, but ReadingQueueTab stays mounted forever too. Also tiny. */
function patchMatchingHits(
  client: QueryClient,
  workspaceId: string,
  match: (hit: Hit) => boolean,
  fields: Partial<Hit>,
) {
  client.setQueriesData<InfiniteData<HitListOut, string | undefined>>(
    { queryKey: keys.searchHitsRoot(workspaceId) },
    (data) =>
      data && {
        ...data,
        pages: data.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => (match(item) ? { ...item, ...fields } : item)),
        })),
      },
  )
  client.invalidateQueries({
    queryKey: keys.searchHitsRoot(workspaceId),
    predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
  })
  client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) })
  client.invalidateQueries({ queryKey: keys.readingQueueRoot(workspaceId) })
  client.invalidateQueries({ queryKey: keys.snowballNext(workspaceId) }) // a decision changes the branch default
}

function patchHitFields(client: QueryClient, workspaceId: string, hitId: string, fields: Partial<Hit>) {
  patchMatchingHits(client, workspaceId, (hit) => hit.id === hitId, fields)
}

/** Whether a cached hit is the one an eligibility update (keyed by paper + run, not hit id) just changed. */
export function matchesEligibleHit(hit: Hit, paperId: string, runId: string): boolean {
  return hit.paper_id === paperId && hit.run_id === runId
}

/** Reviews one hit (the stage-1 triage decision). */
export function usePatchSearchHit(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, body }: { hitId: string; body: HitReviewUpdate }) =>
      api.patchSearchHit(workspaceId, hitId, body),
    onSuccess: (hit) => {
      patchHitFields(client, workspaceId, hit.id, hit)
      client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) })
      client.invalidateQueries({ queryKey: keys.savedSearches(workspaceId) }) // their "N new" counts unscreened hits
    },
  })
}

/** Bulk stage-1 triage (HitTable's multi-select action bar): applies the same relevant/not_relevant/maybe decision
 * to every selected hit in one request, instead of one at a time via the per-row kebab menu. Unlike
 * useImportAllHits/useClearSearchHits, we already know every id this changed — we built `hit_ids` ourselves — so
 * this patches them directly via `patchMatchingHits` (which already invalidates prismaRoot/readingQueueRoot, same
 * as a single patch) instead of resetting/refetching the pool. Mirrors bulk_review_hits' own field semantics
 * exactly: stage1_exclude_reason/priority are only touched when sent, never cleared by omission. */
export function useBulkPatchSearchHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: BulkHitReviewUpdate) => api.bulkPatchSearchHits(workspaceId, body),
    onSuccess: (_result, body) => {
      const ids = new Set(body.hit_ids)
      patchMatchingHits(client, workspaceId, (hit) => ids.has(hit.id), {
        stage1_status: body.stage1_status,
        ...(body.stage1_exclude_reason ? { stage1_exclude_reason: body.stage1_exclude_reason } : {}),
        ...(body.priority != null ? { priority: body.priority } : {}),
      })
      client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) })
      client.invalidateQueries({ queryKey: keys.savedSearches(workspaceId) }) // their "N new" counts unscreened hits
    },
  })
}

/** Accepts the AI's include/exclude suggestion on each given undecided hit (an owner action: the only way a
 * suggestion becomes a decision). Decisions change, so the pool, the ranking and the PRISMA counts reload. */
export function useAcceptSuggestions(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (hitIds: string[]) => api.acceptSuggestions(workspaceId, hitIds),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.readingQueueRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.snowballNext(workspaceId) }),
      ]),
  })
}

/** Imports one hit into the corpus (the only way the UI calls this — HitTable's per-hit "Add PDF" button; see its
 * docstring for why this is never a bulk action). The import response only carries counts, not the updated hit,
 * so this derives the new `acquisition_status` from them directly: `imported` and `failed` are each 0 or 1 for a
 * single targeted hit, and exactly one of them is 1 — `failed` here means no free copy was found automatically,
 * not a request error, so it resolves rather than rejects (HitPreview keeps offering the manual options). */
export function useImportSearchHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (hitIds: [string]) => api.importSearchHits(workspaceId, hitIds),
    onSuccess: (result, [hitId]) =>
      patchHitFields(client, workspaceId, hitId, { acquisition_status: result.imported > 0 ? 'imported' : 'failed' }),
  })
}

/** Imports every hit still pending acquisition in the current (unfiltered) pool — the deliberate "bulk" action
 * behind HitTable's "Import all with PDF in this filter" button, as opposed to `useImportSearchHits`'s one-hit-at-
 * a-time "Add PDF". The response carries no ids of what changed (could be many hits at once), so there's nothing
 * to patch — same reasoning as `useSnowball`'s reset: drop the unfiltered pool's own query back to page 1 and
 * re-fetch just that (never a blanket `invalidateQueries` over the whole family, which would re-fetch every
 * already-loaded page of a pool that can run into the thousands), plus a real, cheap refetch of any filtered
 * view whose membership could have shifted (e.g. ManualAcquisitionTab's `'failed'` filter). */
export function useImportAllHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.importSearchHits(workspaceId, undefined),
    onSuccess: () =>
      Promise.all([
        client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }),
        client.invalidateQueries({
          queryKey: keys.searchHitsRoot(workspaceId),
          predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
        }),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.readingQueueRoot(workspaceId) }),
      ]),
  })
}

/** Deletes every hit not yet imported or manually acquired — the pool's own "start over" action. Same reset
 * (never invalidate) treatment of the big unfiltered pool as `useImportAllHits`, for the same reason: this can
 * change every row in it at once, and invalidating an infinite query re-fetches every already-loaded page. */
export function useClearSearchHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.clearSearchHits(workspaceId),
    onSuccess: () =>
      Promise.all([
        client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }),
        client.invalidateQueries({
          queryKey: keys.searchHitsRoot(workspaceId),
          predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
        }),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.readingQueueRoot(workspaceId) }),
      ]),
  })
}

/** Manual acquisition (Task 10): uploads a PDF for one hit that had no free download. */
export function useUploadHitPdf(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, file }: { hitId: string; file: File }) => api.uploadHitPdf(workspaceId, hitId, file),
    onSuccess: (hit) => {
      patchHitFields(client, workspaceId, hit.id, hit)
      // An upload onto a hit whose paper was saved without a PDF attaches it: the library and reader must see that.
      if (hit.paper_id) {
        void client.invalidateQueries({ queryKey: keys.papers })
        void client.invalidateQueries({ queryKey: keys.paper(hit.paper_id) })
      }
    },
    onError: (error: Error) => {
      // A stale awaiting row: its paper got a PDF elsewhere. The hit and paper views catch up (no paper id here).
      if (error.message === 'already_has_pdf') {
        void client.invalidateQueries({ queryKey: keys.workspaces })
        void client.invalidateQueries({ queryKey: keys.papers })
      }
    },
  })
}

/** Sets a paper's stage-2 eligibility for one search run. The response is a full `EligibilityOut`, not a hit, so
 * this patches its `stage2_status`/`stage2_exclude_reason` onto every cached hit whose `(paper_id, run_id)`
 * matches `(paper_id, search_run_id)` from the response — never by `hit.id`, which the response doesn't carry.
 * Same filtered-views-only real invalidate as `patchHitFields`; see `patchMatchingHits`'s docstring above. */
export function useSetEligibility(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ paperId, runId, body }: { paperId: string; runId: string; body: EligibilityUpdate }) =>
      api.setEligibility(workspaceId, paperId, runId, body),
    onSuccess: (out) =>
      patchMatchingHits(client, workspaceId, (hit) => matchesEligibleHit(hit, out.paper_id, out.search_run_id), {
        stage2_status: out.stage2_status,
        stage2_exclude_reason: out.stage2_exclude_reason,
      }),
  })
}

/** Runs backward/forward snowballing from a set of seed papers. The response (`new_hits`, `skipped_seeds`,
 * `errors`) carries no ids of what it created, so there's nothing to patch — the counts are surfaced directly
 * from this mutation's own `.data`/`.isSuccess`/`.isError` by ScreeningTab, the same way `HitTable` already
 * reads `useImportSearchHits`'s `failed` count from mutation state without any cache patching.
 *
 * `onSuccess` always invalidates `prismaRoot` and `readingQueueRoot`: a snowballed hit can shift the PRISMA
 * funnel's counts and, once screened and imported, the reading queue's rows, and both PrismaTab and
 * ReadingQueueTab stay mounted forever (`WorkspacePage`'s `forceMount`), so neither query ever refetches on its
 * own without this.
 *
 * When `new_hits > 0`, it also *resets* — `exact: true`, one query, never the whole family — the unfiltered
 * pool's own query (`searchHits(workspaceId, 'all', 'all')`). Without this, a snowballed hit was invisible in
 * the Search tab until an unrelated refetch or a full reload: nothing else marks that query stale. `reset`, not
 * `invalidate`: invalidating an infinite query re-fetches every already-loaded page — the exact request storm
 * `patchMatchingHits`'s docstring describes for a pool that can run into the thousands of hits across dozens of
 * pages — while resetting drops it back to just page 1 and re-fetches only that. HARD RULE: never
 * `invalidateQueries({ queryKey: searchHitsRoot(workspaceId) })` here, or any other filtered variant — a
 * snowball call can run while the Search tab's big unfiltered pool (or a filtered tab) is mounted too, and a
 * wholesale invalidate would re-trigger a full refetch on every click. */
export function useSnowball(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SnowballRequest) => api.snowball(workspaceId, body),
    onSuccess: (result) => {
      const work = [
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.readingQueueRoot(workspaceId) }),
        client.invalidateQueries({ queryKey: keys.snowballNext(workspaceId) }),
      ]
      if (result.new_hits > 0) {
        work.push(client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }))
      }
      return Promise.all(work)
    },
  })
}

/** The PRISMA flow-diagram counts (`runs`: a single run id, or `'all'` to combine every run in the workspace). */
export function usePrismaExport(workspaceId: string, runs: string) {
  return useQuery({
    queryKey: keys.prisma(workspaceId, runs),
    queryFn: () => api.prismaExport(workspaceId, runs),
  })
}

export const useReadingContext = (paperId: string) =>
  useQuery({ queryKey: keys.readingContext(paperId), queryFn: () => api.readingContext(paperId) })

/** Shared by `useReadingQueue` and ReadingQueueTab's per-run "has included papers" probes, so both hit one cache entry. */
export const readingQueueOptions = (workspaceId: string, runId: string) => ({
  queryKey: keys.readingQueue(workspaceId, runId),
  queryFn: () => api.readingQueue(workspaceId, runId),
})

export const useReadingQueue = (workspaceId: string, runId: string | null, enabled = true) =>
  useQuery({
    ...readingQueueOptions(workspaceId, runId ?? 'none'),
    enabled: enabled && runId != null,
  })
