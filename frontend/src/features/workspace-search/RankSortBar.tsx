import type { RankedHits } from '@/api/client'
import type { HitSort } from './hitSort'

/** The hit pool's sort choice and, in ranked order, what the ranking knows so far (M31a). Text only: the stop hint
 * never stops, hides or decides anything (spec §3.2). */
export function RankSortBar({
  sort,
  onSortChange,
  ranked,
}: {
  sort: HitSort
  onSortChange: (sort: HitSort) => void
  ranked?: RankedHits
}) {
  return (
    <div className="flex flex-col gap-1 border-b px-3 py-1 text-xs text-muted-foreground">
      <label className="flex items-center gap-2">
        <span>Sort hits</span>
        <select
          aria-label="Sort hits"
          value={sort}
          onChange={(event) => onSortChange(event.target.value as HitSort)}
          className="h-7 rounded-md border bg-background px-1 text-xs text-foreground"
        >
          <option value="found">Found order</option>
          <option value="ranked">Most likely relevant first</option>
          <option value="year">Newest publication first</option>
        </select>
      </label>
      {sort === 'ranked' && ranked && !ranked.trained && (
        <p>Ranking learns once you've marked at least one hit relevant and one not relevant.</p>
      )}
      {sort === 'ranked' && ranked?.trained && (
        <p>
          Showing the {Math.min(ranked.items.length, 200)} most likely relevant of {ranked.total_unscreened} unscreened.
        </p>
      )}
      {sort === 'ranked' && ranked?.show_stop_hint && (
        <p role="status">
          Your last {ranked.streak} decisions were all not relevant. You may have found most of the relevant papers.
        </p>
      )}
    </div>
  )
}
