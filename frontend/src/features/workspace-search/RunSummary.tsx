import { Button } from '@/components/ui/button'

const day = (iso: string) => new Date(iso).toLocaleDateString('en', { dateStyle: 'medium' })

/** Names the run whose card is open above the hit list, or says the list spans every run. */
export function RunSummary({
  run,
  resultCount,
  onChangeRun,
}: {
  run: { query_text: string; started_at: string } | null
  resultCount?: number
  onChangeRun: () => void
}) {
  return (
    <div className="flex items-center gap-2 border-b px-3 py-1 text-sm text-muted-foreground">
      <p className="min-w-0 flex-1 truncate">
        {run
          ? `Results from ${run.query_text} · run on ${day(run.started_at)}${
              resultCount === undefined ? '' : ` · ${resultCount.toLocaleString('en')} ${resultCount === 1 ? 'result' : 'results'}`
            }`
          : 'Showing results from every run'}
      </p>
      <Button variant="ghost" size="sm" onClick={onChangeRun}>Change run</Button>
    </div>
  )
}
