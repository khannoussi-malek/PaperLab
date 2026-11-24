import { type InfiniteData, QueryClient, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { BulkHitReviewUpdate, EligibilityUpdate, Hit, HitListOut, HitReviewUpdate, SavedSearchInbox } from '@/entities'
import { api } from '@/services/api'
import { keys } from './core'
import { refreshTree } from './snowball'

/** One hit for the tree's side panel. Nested under the provenance key so every tree refresh re-reads it. */
export const useSearchHit = (workspaceId: string, hitId: string | null) =>
  useQuery({
    queryKey: [...keys.provenance(workspaceId), 'hit', hitId],
    queryFn: () => api.getSearchHit(workspaceId, hitId!),
    enabled: hitId !== null,
  })

/** "Summarise now": the AI reads one hit against the review question. Overwrites its suggestion; the tree re-reads it. */
export function useSuggestHit(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, confirmRemote }: { hitId: string; confirmRemote?: boolean }) => api.suggestHit(workspaceId, hitId, confirmRemote),
    onSuccess: () => refreshTree(client, workspaceId),
  })
}

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
