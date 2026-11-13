import { useSavedSearches, useSearchHits } from '@/api/queries'
import type { WorkspaceTab } from '@/lib/route'

/** Badge counts for the tabs that have one: Search counts saved searches' new finds (M7.6). A paper saved without its PDF waits under Get PDFs
 * (`acquisition`), never as a pending verdict (`screening`). Same `useSearchHits` calls as ManualAcquisitionTab and
 * ScreeningTab, so React Query serves both from one cache. A count is left out while more pages remain, since
 * the true number isn't known yet. */
export function useStepCounts(workspaceId: string): Partial<Record<WorkspaceTab, number>> {
  const failed = useSearchHits(workspaceId, undefined, 'failed')
  const awaiting = useSearchHits(workspaceId, undefined, 'awaiting_pdf')
  const imported = useSearchHits(workspaceId, 'relevant', 'imported')
  const manual = useSearchHits(workspaceId, 'relevant', 'manual')
  const rows = (q: typeof failed) => q.data?.pages.flatMap((page) => page.items) ?? []
  const toReview = [...rows(imported), ...rows(manual)].filter((hit) => !hit.stage2_status).length
  const newFinds = (useSavedSearches(workspaceId).data ?? []).reduce((sum, saved) => sum + saved.new_hits, 0)
  return {
    ...(newFinds > 0 ? { search: newFinds } : {}),
    ...(failed.data && awaiting.data && !failed.hasNextPage && !awaiting.hasNextPage
      ? { acquisition: rows(failed).length + rows(awaiting).length }
      : {}),
    ...(imported.data && manual.data && !imported.hasNextPage && !manual.hasNextPage ? { screening: toReview } : {}),
  }
}
