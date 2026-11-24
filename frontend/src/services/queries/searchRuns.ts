import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { SearchRun, SearchRunCreate, SearchRunSummary } from '@/entities'
import { api } from '@/services/api'
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

/** The workspace's recent runs, newest first; polls only while one is still running. */
export const useSearchRuns = (workspaceId: string) =>
  useQuery({
    queryKey: keys.searchRuns(workspaceId),
    queryFn: () => api.listSearchRuns(workspaceId),
    refetchInterval: (query) =>
      query.state.data?.some((r: SearchRunSummary) => r.status === 'running') ? PAPERS_POLL_MS : false,
  })

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
