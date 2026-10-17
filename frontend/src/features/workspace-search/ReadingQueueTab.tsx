import { useEffect, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { readingQueueOptions, usePrismaExport, useReadingQueue } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { readingChip } from '@/features/reading/passes'
import { LoadError } from '@/features/library/ErrorAlert'
import { EmptyState, GoToSearchAction, TabSkeleton } from '@/features/workspaces/TabStates'
import { counted } from '@/features/workspaces/workspaceMeta'
import { readerHref } from '@/lib/route'
import { asPrismaRunMeta, type PrismaRunMeta } from './prismaRunMeta'

const PROBED_RUNS = 10

/** Which run the reading list opens on (§11.2): the user's pick, then the URL run if it has included papers, then
 * the newest of the 10 newest runs that has some, then simply the newest. `hasIncludes` is `undefined` while a
 * probe is still loading; we return null (wait) rather than fall back early. */
export function pickReadingRun(
  runs: PrismaRunMeta[],
  picked: string | null,
  urlRun: string | null,
  hasIncludes: (id: string) => boolean | undefined,
): string | null {
  if (picked) return picked
  const newest = runs.toSorted((a, b) => b.started_at.localeCompare(a.started_at))
  const candidates = [...(urlRun && runs.some((r) => r.id === urlRun) ? [urlRun] : []), ...newest.slice(0, PROBED_RUNS).map((r) => r.id)]
  for (const id of candidates) {
    const has = hasIncludes(id)
    if (has === undefined) return null
    if (has) return id
  }
  return newest[0]?.id ?? null
}

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
  // The automatic choice, pinned once made (for the URL run it was made under) so later invalidations of the
  // reading-queue queries (every Relevant/Not relevant click) don't re-run the probes or flip the selection.
  const [pinned, setPinned] = useState<{ urlRun: string | null; id: string } | null>(null)
  const autoRunId = pinned && pinned.urlRun === runId ? pinned.id : null
  const { data: allRunsData, isPending: runsPending, isError: runsError, error: runsErr, refetch: refetchRuns } = usePrismaExport(workspaceId, 'all')
  const allRuns = allRunsData ? asPrismaRunMeta(allRunsData.runs) : []
  const newestIds = allRuns.toSorted((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, PROBED_RUNS).map((r) => r.id)
  const probeIds = [...new Set([...(runId && allRuns.some((r) => r.id === runId) ? [runId] : []), ...newestIds])]
  const probes = useQueries({
    queries: probeIds.map((id) => ({ ...readingQueueOptions(workspaceId, id), enabled: manualRunId == null && autoRunId == null })),
  })
  const hasIncludes = (id: string) => {
    const q = probes[probeIds.indexOf(id)]
    return q?.isError ? false : q?.data ? q.data.rows.length > 0 : undefined
  }
  const picked = pickReadingRun(allRuns, manualRunId ?? autoRunId, runId, hasIncludes)
  const selectedRunId = picked
  useEffect(() => {
    if (manualRunId == null && autoRunId == null && picked != null) setPinned({ urlRun: runId, id: picked })
  }, [manualRunId, autoRunId, picked, runId])

  const queue = useReadingQueue(workspaceId, selectedRunId, selectedRunId != null)

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

  if (selectedRunId == null) return <TabSkeleton label="Loading reading list" />

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <p className="max-w-prose text-sm text-muted-foreground">
        Only papers you included in step 3 appear here. Papers added on the Papers tab aren't part of the review flow.
      </p>
      <label className="flex w-fit items-center gap-2 text-sm">
        <span>Run</span>
        <select
          value={selectedRunId}
          onChange={(e) => setManualRunId(e.target.value)}
          className="w-fit rounded-md border border-input bg-background px-2 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
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
