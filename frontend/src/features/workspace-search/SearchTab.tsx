import { useState } from 'react'
import { useSearchRun, useStartSearchRun } from '@/api/queries'
import { SearchControls } from './SearchControls'
import { HitTable } from './HitTable'

export function SearchTab({ workspaceId }: { workspaceId: string }) {
  const [runId, setRunId] = useState<string | null>(null)
  const startRun = useStartSearchRun(workspaceId)
  const run = useSearchRun(workspaceId, runId)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SearchControls
        isRunning={run.data?.status === 'running'}
        onStart={(args) => startRun.mutate(args, { onSuccess: (created) => setRunId(created.id) })}
      />
      {run.data && (
        <div className="border-b px-3 py-1 text-sm text-muted-foreground">
          {run.data.status} · {(run.data.stats_json?.last_batch_new_hits as number | undefined) ?? 0} new in last
          batch
        </div>
      )}
      <HitTable workspaceId={workspaceId} />
    </div>
  )
}
