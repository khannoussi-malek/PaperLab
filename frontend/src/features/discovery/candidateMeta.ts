import type { Candidate } from '@/api/client'

/** "1,234 citations", "1 citation", or '' when the count is unknown. */
export const citationsLabel = (count: number | null): string =>
  count === null ? '' : `${count.toLocaleString('en-US')} ${count === 1 ? 'citation' : 'citations'}`

/** Where "Open page" goes: the DOI, else arXiv, else OpenAlex, else Semantic Scholar; null with no identifier. */
export function pageLink(candidate: Pick<Candidate, 'doi' | 'arxiv_id' | 'openalex_id' | 's2_id'>): string | null {
  if (candidate.doi) return `https://doi.org/${candidate.doi}`
  if (candidate.arxiv_id) return `https://arxiv.org/abs/${candidate.arxiv_id}`
  if (candidate.openalex_id) return `https://openalex.org/${candidate.openalex_id}`
  if (candidate.s2_id) return `https://www.semanticscholar.org/paper/${candidate.s2_id}`
  return null
}

/** A React key that survives a refetch: the first identifier the candidate has, else its position. */
export const candidateKey = (candidate: Candidate, index: number): string =>
  candidate.openalex_id ?? candidate.s2_id ?? candidate.doi ?? `row-${index}`
