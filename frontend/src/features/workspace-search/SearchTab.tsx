import { useRef, useState } from 'react'
import { useContinueSearchRun, useSearchRun, useSearchRuns, useStartSearchRun, useStopSearchRun, type SavedSearchInbox } from '@/api/queries'
import { Scene3D } from '@/features/scene3d/Scene3D'
import type { SearchRunStatus } from '@/features/scene3d/poses'
import { SearchControls } from './SearchControls'
import { HitTable } from './HitTable'
import { SavedSearches } from './SavedSearches'
import { RunsList } from './RunsList'
import { RunSummary } from './RunSummary'
import { Button } from '@/components/ui/button'
import { continueLabel, continueRefusal, pausedText } from './continueText'
import { ScreeningAssist } from './ScreeningAssist'
import { SourceResults } from './SourceResults'

// Module level, so the scene never restarts on a re-render.
const loadSearchRunScene = () => import('@/features/scene3d/directors/searchRun')

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
  const continueRun = useContinueSearchRun(workspaceId)
  const run = useSearchRun(workspaceId, runId)
  const [query, setQuery] = useState('')
  const [runsOpen, setRunsOpen] = useState(false)
  const [inbox, setInbox] = useState<SavedSearchInbox | null>(null)
  const runsQuery = useSearchRuns(workspaceId)
  const runCount = runsQuery.data?.find((r) => r.id === runId)?.hit_count
  const runsToggle = useRef<HTMLButtonElement>(null)
  const changeRun = () => {
    setRunsOpen(true)
    runsToggle.current?.scrollIntoView({ block: 'nearest' })
    runsToggle.current?.focus()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <SearchControls
        isRunning={run.data?.status === 'running'}
        onQueryChange={setQuery}
        error={startRun.error?.message}
        onStart={(args) => startRun.mutate(args, { onSuccess: (created) => onRunIdChange(created.id) })}
        onStop={() => runId && stopRun.mutate(runId)}
      />
      <SavedSearches workspaceId={workspaceId} currentQuery={query} onRunStarted={onRunIdChange} onShowNew={setInbox} />
      <RunsList workspaceId={workspaceId} runId={runId} onSelect={onRunIdChange} open={runsOpen} onOpenChange={setRunsOpen} toggleRef={runsToggle} />
      <ScreeningAssist workspaceId={workspaceId} />
      {run.data && (
        <>
        <div className="flex items-center gap-2 border-b px-3 py-1 text-sm text-muted-foreground">
          <Scene3D
            load={loadSearchRunScene}
            input={{ status: run.data.status as SearchRunStatus }}
            fallback={null}
            className="size-8"
          />
          {pausedText(run.data) ?? run.data.status} · {(run.data.stats_json?.last_batch_new_hits as number | undefined) ?? 0} new in last
          batch
          {run.data.stats_json?.cut_short === true && run.data.stopped_at && (
            <span className="ml-2">
              Stopped early after {Math.round((Date.parse(run.data.stopped_at) - Date.parse(run.data.started_at)) / 60000)} min —{' '}
              {((run.data.stats_json.unfinished_sources as string[] | undefined) ?? []).length} sources not finished
            </span>
          )}
          {run.data.can_continue && (
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              aria-label={continueLabel(run.data.sources_left)}
              disabled={continueRun.isPending}
              onClick={() => continueRun.mutate(run.data.id)}
            >
              Continue
            </Button>
          )}
        </div>
        {continueRun.error && continueRun.variables === run.data.id && (
          <div role="alert" className="border-b px-3 py-1 text-sm text-destructive">
            {continueRefusal(continueRun.error.message)}
          </div>
        )}
        <SourceResults run={run.data} />
        </>
      )}
      <RunSummary run={run.data ?? null} resultCount={runCount} hasRuns={(runsQuery.data?.length ?? 0) > 0} onChangeRun={changeRun} />
      <HitTable workspaceId={workspaceId} run={run.data} inbox={inbox ?? undefined} onLeaveInbox={() => setInbox(null)} />
    </div>
  )
}
