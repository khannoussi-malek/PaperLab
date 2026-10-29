import { useTriageEvents } from '@/api/queries'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { describeEvent } from './historyText'

/** Every change to a paper's reading state, newest first. A paper decided before the history existed has none. */
export function ReadingHistory({ paperId, enabled = true }: { paperId: string; enabled?: boolean }) {
  const { data, error } = useTriageEvents(paperId, enabled)
  const events = [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))
  return (
    <section aria-labelledby="reading-history-heading" className="mt-3">
      <h3 id="reading-history-heading" className="text-sm font-medium">
        History
      </h3>
      {error ? (
        <ErrorAlert message={error.message} />
      ) : data && events.length === 0 ? (
        <p className="mt-1.5 text-sm text-muted-foreground">No changes recorded yet.</p>
      ) : (
        <ol className="mt-1.5 space-y-1 text-sm">
          {events.map((e) => {
            const row = describeEvent(e)
            return (
              <li key={e.id} className="tabular-nums">
                {[row.when, row.what, row.why, row.where].filter(Boolean).join(' · ')}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
