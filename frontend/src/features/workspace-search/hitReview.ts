/** Stage-1 exclusion reasons, shared by HitMenu's "Not relevant…" submenu and HitPreview's reason select —
 * kept out of either component file so Fast Refresh doesn't warn about a non-component export. */
export const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const

/** Display names for `Hit.sources` — every provider that has matched this paper (ExternalRef.sources, trust-order
 * first), shared by HitTable's row label and HitPreview's panel. Falls back to the raw id for anything unlisted
 * (new providers land here eventually, but a hit should never go unlabeled while it does). */
const SOURCE_LABELS: Record<string, string> = {
  openalex: 'OpenAlex',
  crossref: 'Crossref',
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  core: 'CORE',
  unpaywall: 'Unpaywall',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}
