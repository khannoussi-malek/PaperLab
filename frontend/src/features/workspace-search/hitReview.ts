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
