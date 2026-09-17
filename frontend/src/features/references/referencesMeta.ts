import type { Reference, References } from '@/api/client'

const COCITATION_BADGE_MIN = 2

/** "{refs} cited by 3+ of your papers, {pdfs} have PDFs", dropping either half whose count is zero, and the whole
 * line when both are. */
export function summaryLine(summary: References['summary']): string | null {
  const parts = [
    summary.cited_by_3plus > 0 ? `${summary.cited_by_3plus} cited by 3+ of your papers` : null,
    summary.with_pdf > 0 ? `${summary.with_pdf} have PDFs` : null,
  ].filter((part): part is string => part !== null)
  return parts.length > 0 ? parts.join(', ') : null
}

/** "Cited by {n} of your papers", only once at least 2 of the reader's own papers cite it. */
export const cocitationBadge = (cocitation: number): string | null =>
  cocitation >= COCITATION_BADGE_MIN ? `Cited by ${cocitation} of your papers` : null

/** A row's primary action: already in the library, or importable (a free PDF is listed) — else null, since neither
 * applies. Open page is independent of this (as in CandidateRow): it shows whenever an identifier links to one. */
export function rowAction(reference: Pick<Reference, 'paper_id' | 'has_pdf'>): 'in-library' | 'import' | null {
  if (reference.paper_id) return 'in-library'
  if (reference.has_pdf) return 'import'
  return null
}
