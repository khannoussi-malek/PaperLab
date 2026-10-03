import { useState } from 'react'
import { usePrismaExport, useReadingQueue } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { readingChip } from '@/features/reading/passes'
import { counted } from '@/features/workspaces/workspaceMeta'
import { readerHref } from '@/lib/route'
import { asPrismaRunMeta } from './prismaRunMeta'

/** How much of this search run's included papers have actually been read (M30 §12): one row per stage-2-included,
 * already-imported paper, its priority, and its reading progress.
 *
 * Which run is "active" can't come from the URL alone (`runId`, carried in from the Search tab's own last-started
 * run) — every normal way back into a workspace (the sidebar, a bookmark, the reader banner's own workspace link)
 * drops it, and there's no Search-tab control to pick a past run either. So this tab keeps its own run picker,
 * backed by `usePrismaExport(workspaceId, 'all')`'s `runs` list — the only existing endpoint that already returns a
 * workspace's past runs (PrismaTab's own precedent) — rather than inventing a new one. `manualRunId` is null until
 * the picker is touched, so the effective selection prefers (in order): an explicit pick, the `runId` prop (so a
 * freshly-started run or a bookmarked URL still works), then the most recently started run, with no `useEffect`
 * needed — it's derived fresh every render. */
export function ReadingQueueTab({ workspaceId, runId }: { workspaceId: string; runId: string | null }) {
  const [manualRunId, setManualRunId] = useState<string | null>(null)
  const { data: allRunsData, isPending: runsPending } = usePrismaExport(workspaceId, 'all')
  const allRuns = allRunsData ? asPrismaRunMeta(allRunsData.runs) : []
  const mostRecent = allRuns.toSorted((a, b) => b.started_at.localeCompare(a.started_at))[0]
  const selectedRunId = manualRunId ?? runId ?? mostRecent?.id ?? null

  const queue = useReadingQueue(workspaceId, selectedRunId, selectedRunId != null)

  if (runsPending) {
    return <p className="p-4 text-sm text-muted-foreground">Loading…</p>
  }
  if (allRuns.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">No search runs yet. Start one on the Search tab.</p>
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <label className="flex w-fit items-center gap-2 text-sm">
        <span>Run</span>
        <select
          value={selectedRunId ?? ''}
          onChange={(e) => setManualRunId(e.target.value)}
          className="w-fit rounded-md border border-input bg-background px-2 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {allRuns.map((r) => (
            <option key={r.id} value={r.id}>{r.query_text}</option>
          ))}
        </select>
      </label>
      {queue.isError && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{queue.error.message}</AlertDescription>
        </Alert>
      )}
      {!queue.isError && queue.data === undefined && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {queue.data?.rows.length === 0 && (
        <p className="text-sm text-muted-foreground">No included papers have been imported into the library yet.</p>
      )}
      {queue.data && queue.data.rows.length > 0 && (
        <ul className="reading-queue divide-y divide-glass-border rounded-lg border">
          {queue.data.rows.map((row) => (
            <li key={row.paper_id} className="flex items-center gap-3 px-4 py-2 transition-colors hover:bg-muted/40">
              <a href={readerHref(row.paper_id)} className="min-w-0 flex-1 truncate text-sm font-medium hover:underline">
                {row.title}
              </a>
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
