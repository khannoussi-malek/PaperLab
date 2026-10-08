import type { Hit } from '@/api/client'
import { SOURCE_NAMES } from '@/features/discovery/candidateMeta'

/** Stage-1 exclusion reasons, shared by HitMenu's "Not relevant…" submenu and HitPreview's reason select —
 * kept out of either component file so Fast Refresh doesn't warn about a non-component export. */
export const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const

/** Display name for one of `Hit.sources` — every provider that has matched this paper (ExternalRef.sources,
 * trust-order first), shared by HitTable's row label and HitPreview's panel. Reuses candidateMeta's own
 * SOURCE_NAMES instead of a second, independently-maintained copy. Falls back to the raw id for anything unlisted
 * — `Hit.sources` stays a loose string[] (not a Literal union), so a hit can carry a source id the registry has
 * since removed; it should never go unlabeled for that. */
export function sourceLabel(source: string): string {
  return (SOURCE_NAMES as Record<string, string>)[source] ?? source
}

/** Matches a filter box's text against a hit's title and abstract — shared by HitTable and ScreeningTab, so both
 * filter boxes behave the same way. Whichever provider supplied the abstract, a search term can turn up there
 * even when the title doesn't mention it, so a title-only match would miss it. */
export function matchesFilter(hit: Hit, filter: string): boolean {
  const title = (hit.title ?? hit.normalized_title).toLowerCase()
  const abstract = hit.abstract?.toLowerCase() ?? ''
  return title.includes(filter) || abstract.includes(filter)
}
