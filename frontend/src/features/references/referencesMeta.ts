import type { Reference, References, ReferencesDirection } from '@/api/client'

const COCITATION_BADGE_MIN = 2

/** "{refs} cited by 3+ of your papers, {pdfs} have PDFs", or "{refs} cite 3+ of your papers" for citing works (their
 * count is the library papers they cite). Either half drops when its count is zero, and the whole line when both do. */
export function summaryLine(summary: References['summary'], direction: ReferencesDirection): string | null {
  const shared = direction === 'cites' ? 'cited by' : 'cite'
  const parts = [
    summary.cited_by_3plus > 0 ? `${summary.cited_by_3plus} ${shared} 3+ of your papers` : null,
    summary.with_pdf > 0 ? `${summary.with_pdf} have PDFs` : null,
  ].filter((part): part is string => part !== null)
  return parts.length > 0 ? parts.join(', ') : null
}

/** "Cited by {n} of your papers" for a reference, "Cites {n} of your papers" for a citing work, only once the count
 * reaches 2 (the paper being read is always one of them). */
export function cocitationBadge(cocitation: number, direction: ReferencesDirection): string | null {
  if (cocitation < COCITATION_BADGE_MIN) return null
  return direction === 'cites' ? `Cited by ${cocitation} of your papers` : `Cites ${cocitation} of your papers`
}

/** A row's primary action: already in the library, or importable (a free PDF is listed) — else null, since neither
 * applies. Open page is independent of this (as in CandidateRow): it shows whenever an identifier links to one. */
export function rowAction(reference: Pick<Reference, 'paper_id' | 'has_pdf'>): 'in-library' | 'import' | null {
  if (reference.paper_id) return 'in-library'
  if (reference.has_pdf) return 'import'
  return null
}
