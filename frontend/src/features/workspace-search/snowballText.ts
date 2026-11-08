import type { SnowballStats } from '@/api/client'

const S2_REFUSED = 'Semantic Scholar refused: add a free key in Settings → Paper sources.'

/** Plain words for a Semantic Scholar 429/401; anything else is shown as-is. */
export const friendlySnowballError = (raw: string) => (/\b(429|401)\b/.test(raw) ? S2_REFUSED : raw)

/** The Runs-list summary of a snowball run: counts over all seeds, and the first seed error if any. */
export function snowballLine(s: SnowballStats): { counts: string; error: string | null } {
  const sum = (k: 'cites' | 'cited_by') => s.seeds.reduce((n, x) => n + x.found[k], 0)
  const skipped = s.seeds.filter((x) => x.skipped !== null).length
  const err = s.seeds.find((x) => x.error)?.error ?? null
  return {
    counts: `${sum('cited_by')} citing · ${sum('cites')} cited · ${skipped} skipped`,
    error: err === null ? null : friendlySnowballError(err),
  }
}
