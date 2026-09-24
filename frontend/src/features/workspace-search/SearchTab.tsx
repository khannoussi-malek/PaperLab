import { useNewHitsAvailable, useRefreshHits, useSearchRun, useStartSearchRun, useStopSearchRun } from '@/api/queries'
import { Button } from '@/components/ui/button'
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
  // The hit pool has no poll of its own. It doesn't auto-refresh on progress (a pool can reach 3,000+ hits across
  // dozens of pages, and re-fetching all of them on every tick of a long-running real search froze the UI) — this
  // only signals that new hits exist; refreshHits() pays the real cost once, when the user actually asks for it.
  const newHits = useNewHitsAvailable(run.data)
  const refreshHits = useRefreshHits(workspaceId)

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
      {newHits.available && (
        <div className="flex items-center justify-between border-b bg-muted/50 px-3 py-1 text-sm">
          <span>New hits found</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              newHits.acknowledge()
              refreshHits()
            }}
          >
            Refresh
          </Button>
        </div>
      )}
      <HitTable workspaceId={workspaceId} />
    </div>
  )
}
