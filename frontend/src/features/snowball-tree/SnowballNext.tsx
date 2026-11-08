import { useRunSnowballNext, useSnowballNext } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { friendlySnowballError } from '@/features/workspace-search/snowballText'

const WORD: Record<string, string> = { cites: 'Its references', cited_by: 'Papers citing it' }

/** Branches marked "Go further" that still have a direction to snowball, with one button to run them all. */
export function SnowballNext({ workspaceId }: { workspaceId: string }) {
  const items = useSnowballNext(workspaceId).data
  const run = useRunSnowballNext(workspaceId)
  if ((!items || items.length === 0) && !run.data) return null
  const list = items ?? []
  const error = Object.values(run.data?.errors ?? {}).find(Boolean)
  return (
    <section aria-label="Snowball next" className="rounded-lg border border-border bg-card p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-heading text-base">Snowball next ({list.length})</h3>
        {list.length > 0 && (
          <Button type="button" size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? 'Snowballing…' : 'Run all'}
          </Button>
        )}
      </div>
      <ul className="mt-2 max-h-32 space-y-1 overflow-auto text-xs">
        {list.map((i) => (
          <li key={i.hit_id ?? i.paper_id} className="flex justify-between gap-3">
            <span className="min-w-0 truncate">{i.title}</span>
            <span className="shrink-0 text-muted-foreground">{i.directions_left.map((d) => WORD[d] ?? d).join(', ')}</span>
          </li>
        ))}
      </ul>
      {run.data && (
        <p className="mt-2 text-xs text-muted-foreground">
          {run.data.new_hits} new papers{error ? `. ${friendlySnowballError(error)}` : ''}
        </p>
      )}
      {(run.data?.remaining ?? 0) > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">{run.data!.remaining} more left: Run all again</p>
      )}
      {run.isError && <p role="alert" className="mt-2 text-xs text-destructive">{run.error.message}</p>}
    </section>
  )
}
