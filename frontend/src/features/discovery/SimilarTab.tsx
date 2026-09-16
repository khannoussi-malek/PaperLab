import { useSimilarPapers } from '@/api/queries'
import { LoadError } from '@/features/library/ErrorAlert'
import { CandidateList } from './CandidateList'

/** The reader's Similar tab. Asks Semantic Scholar only once the tab has been opened. */
export function SimilarTab({ paperId, active }: { paperId: string; active: boolean }) {
  const similar = useSimilarPapers(paperId, active)
  return (
    // RightPanel draws the glass and the border, as for Notes and Data.
    <aside className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4" aria-label="Similar papers">
      <p className="text-sm text-muted-foreground">Papers like this one, suggested by Semantic Scholar.</p>
      {similar.isError ? (
        <LoadError message={similar.error.message} onRetry={() => void similar.refetch()} />
      ) : similar.data === undefined ? (
        <p className="text-muted-foreground">Finding similar papers…</p>
      ) : (
        <CandidateList candidates={similar.data} empty="Semantic Scholar has no suggestions for this paper." />
      )}
    </aside>
  )
}
