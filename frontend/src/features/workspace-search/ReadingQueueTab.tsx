import { useReadingQueue } from '@/api/queries'
import { readingChip } from '@/features/reading/passes'
import { readerHref } from '@/lib/route'

/** How much of this search run's included papers have actually been read (M30 §12): one row per stage-2-included,
 * already-imported paper, its priority, and its reading progress. Scoped to the workspace's active run — no run
 * selected yet shows a prompt to pick one on the Search tab instead of an empty table. */
export function ReadingQueueTab({ workspaceId, runId }: { workspaceId: string; runId: string | null }) {
  const queue = useReadingQueue(workspaceId, runId, runId != null)

  if (runId == null) {
    return <p className="p-4 text-sm text-muted-foreground">Pick a search run on the Search tab to see its reading progress.</p>
  }
  if (queue.data === undefined) {
    return <p className="p-4 text-sm text-muted-foreground">Loading…</p>
  }
  if (queue.data.rows.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">No included papers have been imported into the library yet.</p>
  }

  return (
    <ul className="reading-queue divide-y divide-glass-border">
      {queue.data.rows.map((row) => (
        <li key={row.paper_id} className="flex items-center gap-3 px-4 py-2">
          <a href={readerHref(row.paper_id)} className="min-w-0 flex-1 truncate text-sm font-medium hover:underline">
            {row.title}
          </a>
          {row.priority != null && <span className="text-xs text-muted-foreground">Priority {row.priority}</span>}
          <span className="reading-chip text-xs text-muted-foreground">
            {readingChip(row.reading_pass, row.triage as 'keep' | 'later' | 'drop' | null) ?? 'Not started'}
          </span>
          <span className="tabular-nums text-xs text-muted-foreground">{row.note_count} notes</span>
        </li>
      ))}
    </ul>
  )
}
