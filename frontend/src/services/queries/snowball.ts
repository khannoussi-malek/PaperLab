import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { BranchIn, SnowballRequest } from '@/entities'
import { api } from '@/services/api'
import { keys } from './core'

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
