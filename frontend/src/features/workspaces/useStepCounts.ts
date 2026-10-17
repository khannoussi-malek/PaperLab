import { useSearchHits } from '@/api/queries'
import type { WorkspaceTab } from '@/lib/route'

/** Badge counts for the two review tabs that have one. Same `useSearchHits` calls as ManualAcquisitionTab and
 * ScreeningTab, so React Query serves both from one cache. A count is left out while more pages remain, since
 * the true number isn't known yet. */
export function useStepCounts(workspaceId: string): Partial<Record<WorkspaceTab, number>> {
  const failed = useSearchHits(workspaceId, undefined, 'failed')
  const imported = useSearchHits(workspaceId, 'relevant', 'imported')
  const manual = useSearchHits(workspaceId, 'relevant', 'manual')
  const rows = (q: typeof failed) => q.data?.pages.flatMap((page) => page.items) ?? []
  const toReview = [...rows(imported), ...rows(manual)].filter((hit) => !hit.stage2_status).length
  return {
    ...(failed.data && !failed.hasNextPage ? { acquisition: rows(failed).length } : {}),
    ...(imported.data && manual.data && !imported.hasNextPage && !manual.hasNextPage ? { screening: toReview } : {}),
  }
}
