import type { SnowballStats } from '@/api/client'

const S2_REFUSED = 'Semantic Scholar refused: add a free key in Settings → Paper sources.'

// Stored texts look like "HTTP 429 from api.semanticscholar.org" (the app) or "Client error '429 Too Many
// Requests' for url ..." (httpx); a bare number elsewhere (a DOI) is not a status.
const REFUSED = /\bHTTP (429|401)\b|\b(429 Too Many Requests|401 Unauthorized)\b/

/** Plain words for a Semantic Scholar 429/401; anything else is shown as-is. */
export const friendlySnowballError = (raw: string) => (REFUSED.test(raw) ? S2_REFUSED : raw)

export const skippedSeedsText = (n: number) => `Skipped ${n} seed(s) with no Semantic Scholar match.`

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
