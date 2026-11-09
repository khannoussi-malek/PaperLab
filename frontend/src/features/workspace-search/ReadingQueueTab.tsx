import { useState } from 'react'
import { usePrismaExport, useReadingQueue, useWorkspacePapers } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { NoPdfBadge } from '@/features/reader/SourceBadges'
import { readingChip } from '@/features/reading/passes'
import { LoadError } from '@/features/library/ErrorAlert'
import { EmptyState, GoToSearchAction, TabSkeleton } from '@/features/workspaces/TabStates'
import { counted } from '@/features/workspaces/workspaceMeta'
import { readerHref } from '@/lib/route'
import { asPrismaRunMeta } from './prismaRunMeta'

const ALL_RUNS = 'all'

/** One row per stage-2-included, already-imported paper (M30 §12): its priority and reading progress. Defaults to
 * every run in the workspace (an included paper usually belongs to an older run than the newest); the picker
 * narrows it to one run. The run list comes from `usePrismaExport(workspaceId, 'all')`, the only existing endpoint
 * that returns a workspace's past runs. */
export function ReadingQueueTab({ workspaceId, runId }: { workspaceId: string; runId: string | null }) {
  const [selectedRunId, setSelectedRunId] = useState(ALL_RUNS)
  const { data: allRunsData, isPending: runsPending, isError: runsError, error: runsErr, refetch: refetchRuns } = usePrismaExport(workspaceId, 'all')
  const allRuns = allRunsData ? asPrismaRunMeta(allRunsData.runs) : []

  const queue = useReadingQueue(workspaceId, selectedRunId)
  // The queue's rows carry no PDF flag: read it off the workspace's papers (already cached by the Papers tab).
  const noPdfIds = new Set(useWorkspacePapers(workspaceId).data?.filter((p) => p.has_pdf === false).map((p) => p.id))

  if (runsError) {
    return <LoadError message={runsErr.message} onRetry={() => void refetchRuns()} />
  }
  if (runsPending) {
    return <TabSkeleton label="Loading reading list" />
  }
  if (allRuns.length === 0) {
    return (
      <EmptyState title="No search runs yet" action={<GoToSearchAction workspaceId={workspaceId} runId={runId} />}>
        Start one on 1 · Search & screen.
      </EmptyState>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <p className="max-w-prose text-sm text-muted-foreground">
        Only papers you included in step 3 appear here. Papers added on the Papers tab aren't part of the review flow.
      </p>
      <label className="flex w-fit items-center gap-2 text-sm">
        <span>Run</span>
        <select
          value={selectedRunId}
          onChange={(e) => setSelectedRunId(e.target.value)}
          className="w-fit rounded-md border border-input bg-background px-2 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <option value={ALL_RUNS}>All runs</option>
          {allRuns.map((r) => (
            <option key={r.id} value={r.id}>{r.query_text}</option>
          ))}
        </select>
      </label>
      {queue.isError && (
        <LoadError message={queue.error.message} onRetry={() => void queue.refetch()} />
      )}
      {!queue.isError && queue.data === undefined && <TabSkeleton label="Loading reading list" />}
      {queue.data?.rows.length === 0 && (
        <EmptyState title="No included papers yet">No included papers have been imported into the library yet.</EmptyState>
      )}
      {queue.data && queue.data.rows.length > 0 && (
        <ul className="reading-queue divide-y divide-glass-border rounded-lg border">
          {queue.data.rows.map((row) => (
            <li key={row.paper_id} className="flex items-center gap-3 px-4 py-2 transition-colors hover:bg-muted/40">
              <a href={readerHref(row.paper_id)} className="min-w-0 flex-1 truncate text-sm font-medium hover:underline">
                {row.title}
              </a>
              {noPdfIds.has(row.paper_id) && <NoPdfBadge />}
              {row.priority != null && (
                <Badge variant="outline" className="shrink-0 font-normal text-muted-foreground">
                  Priority {row.priority}
                </Badge>
              )}
              <Badge variant="outline" className="reading-chip shrink-0 font-normal text-muted-foreground">
                {readingChip(row.reading_pass, row.triage as 'keep' | 'later' | 'drop' | null) ?? 'Not started'}
              </Badge>
              <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                {counted(row.note_count, 'note')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
