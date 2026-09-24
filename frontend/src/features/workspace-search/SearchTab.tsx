import { useSearchRun, useStartSearchRun, useStopSearchRun } from '@/api/queries'
import { SearchControls } from './SearchControls'
import { HitTable } from './HitTable'

/** `runId` lives in the URL (I1), not local state, so a reload keeps the active run instead of losing it — the
 * caller (WorkspacePage) reads it from the route and reports a new one back via `onRunIdChange`. */
export function SearchTab({
  workspaceId,
  runId,
  onRunIdChange,
}: {
  workspaceId: string
  runId: string | null
  onRunIdChange: (runId: string) => void
}) {
  const startRun = useStartSearchRun(workspaceId)
  const stopRun = useStopSearchRun(workspaceId)
  const run = useSearchRun(workspaceId, runId)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SearchControls
        isRunning={run.data?.status === 'running'}
        onStart={(args) => startRun.mutate(args, { onSuccess: (created) => onRunIdChange(created.id) })}
        onStop={() => runId && stopRun.mutate(runId)}
      />
      {run.data && (
        <div className="border-b px-3 py-1 text-sm text-muted-foreground">
          {run.data.status} · {(run.data.stats_json?.last_batch_new_hits as number | undefined) ?? 0} new in last
          batch
        </div>
      )}
      <HitTable workspaceId={workspaceId} run={run.data} />
    </div>
  )
}
