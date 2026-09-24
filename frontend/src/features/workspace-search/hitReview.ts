/** Stage-1 exclusion reasons, shared by HitMenu's "Not relevant…" submenu and HitPreview's reason select —
 * kept out of either component file so Fast Refresh doesn't warn about a non-component export. */
export const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const
