import type { ChatScope } from '@/api/client'
import { useEmbeddingStatus, useReindexPaper } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { DownloadSearchModel } from '@/features/settings/DownloadSearchModel'
import { SearchRebuild, SourceError } from '@/features/settings/SearchRebuild'
import { READY_AGAIN } from '@/features/settings/searchSources'
import { settingsHref, settingsSectionHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import type { ChatProblem } from './refusals'

export function ProblemAlert({ scope, problem, onRetry }: { scope: ChatScope; problem: ChatProblem; onRetry: () => void }) {
  // Only a paper's `paper_not_indexed` refusal offers Re-index. A hit carries its paper's id once it has a file; none, no button.
  const paperId = scope.kind === 'hit' ? (scope.paperId ?? null) : scope.id
  const reindex = useReindexPaper(paperId ?? '')
  const embedding = useEmbeddingStatus()
  // search_rebuilding (P1): the rebuild's line and bar while it runs, the status polling meanwhile. `undefined` while
  // the status loads counts as still running. Once it is done, say so and offer Retry.
  const waiting = problem.rebuild === true && embedding.data?.rebuild !== null
  const reindexed = reindex.isSuccess ? 'Re-indexing started. Ask again once the paper is ready.' : undefined
  const message = problem.rebuild
    ? waiting
      ? problem.message
      : READY_AGAIN
    : (reindexed ?? reindex.error?.message ?? problem.message)
  return (
    <>
      <Alert variant="destructive" className={cn('chat-error border-glass-border')}>
        <AlertDescription>{waiting ? 'Search is being rebuilt.' : message}</AlertDescription>
        <AlertAction>
          {problem.retryable && !waiting && (
            <Button variant="outline" size="xs" onClick={onRetry}>
              Retry
            </Button>
          )}
          {problem.reindex && paperId !== null && !reindex.isSuccess && (
            <Button variant="outline" size="xs" disabled={reindex.isPending} onClick={() => reindex.mutate()}>
              Re-index
            </Button>
          )}
          {problem.settings && (
            <Button variant="outline" size="xs" asChild>
              <a href={settingsHref}>Open settings</a>
            </Button>
          )}
        </AlertAction>
      </Alert>
      {/* The download block sits outside the alert (not inside it): the alert is role="alert" (assertive, atomic),
          and the download's status line changes every percent, which would re-read the whole alert on each one. */}
      {problem.download && (
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <DownloadSearchModel />
          <a
            href={settingsSectionHref('search')}
            className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Use another search source
          </a>
        </div>
      )}
      {/* Same reason as the download block above: SearchRebuild's line and bar change on every 2 s poll while a
          paper finishes, which would re-read the whole alert on each one if it stayed inside. */}
      {waiting && embedding.data?.rebuild && <SearchRebuild />}
      {/* D155: a paper that keeps failing keeps search paused; the reason and Try again are here too. */}
      {waiting && <SourceError />}
    </>
  )
}
