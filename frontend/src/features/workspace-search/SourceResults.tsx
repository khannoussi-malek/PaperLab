import { SOURCE_NAMES } from '@/features/discovery/candidateMeta'
import type { SearchRun } from '@/api/client'
import { plural } from '@/features/charts/chartMeta'

const STATE_WORDS: Record<string, string> = {
  complete: 'finished',
  paused: 'paused',
  cooling_down: 'still failing',
  gave_up: 'gave up',
  disabled: 'off',
  fetching: 'searching',
}

const sourceName = (id: string) => (Object.hasOwn(SOURCE_NAMES, id) ? SOURCE_NAMES[id as keyof typeof SOURCE_NAMES] : id)

/** What each source did on a run: a run's status only says the job ended, not that the search reached its sources. */
export function SourceResults({ run }: { run: SearchRun }) {
  const results = run.source_results ?? []
  const warnings = run.warnings ?? []
  if (results.length === 0 && warnings.length === 0) return null
  return (
    <section aria-label="What each source did" className="grid gap-1 border-b px-3 py-1.5 text-sm text-muted-foreground">
      {warnings.map((warning) => (
        <p key={warning.source} role="status" className="text-foreground">
          {warning.message}
        </p>
      ))}
      {run.outcome === 'partial' && (
        <p className="font-medium text-foreground">Partial search: not every source finished, so results may be missing.</p>
      )}
      {run.outcome === 'complete' && <p>Every source finished.</p>}
      {results.length > 0 && (
        <ul className="grid gap-0.5">
          {results.map((result) => (
            <li key={result.source}>
              <span className="text-foreground">{sourceName(result.source)}</span>: {STATE_WORDS[result.state] ?? result.state} ·{' '}
              {plural(result.raw_count ?? 0, 'result')}, {result.new_hits ?? 0} new
              {result.reason ? ` · ${result.reason}` : ''}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
