import type { Candidate, PaperSourceId } from '@/api/client'

/** How a source is named on a found paper's badges. */
export const SOURCE_NAMES: Record<PaperSourceId, string> = {
  openalex: 'OpenAlex',
  crossref: 'Crossref',
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  core: 'CORE',
  unpaywall: 'Unpaywall',
}

/** "1,234 citations", "1 citation", or '' when the count is unknown. */
export const citationsLabel = (count: number | null): string =>
  count === null ? '' : `${count.toLocaleString('en-US')} ${count === 1 ? 'citation' : 'citations'}`

/** Where "Open page" goes: the DOI, else arXiv, OpenAlex, Semantic Scholar, then CORE; null with no identifier. */
export function pageLink(
  candidate: Pick<Candidate, 'doi' | 'arxiv_id' | 'openalex_id' | 's2_id' | 'core_id'>,
): string | null {
  if (candidate.doi) return `https://doi.org/${candidate.doi}`
  if (candidate.arxiv_id) return `https://arxiv.org/abs/${candidate.arxiv_id}`
  if (candidate.openalex_id) return `https://openalex.org/${candidate.openalex_id}`
  if (candidate.s2_id) return `https://www.semanticscholar.org/paper/${candidate.s2_id}`
  if (candidate.core_id) return `https://core.ac.uk/works/${candidate.core_id}`
  return null
}

/** A React key that survives a refetch: the first identifier the candidate has, else its position. */
export const candidateKey = (candidate: Candidate, index: number): string =>
  candidate.openalex_id ?? candidate.s2_id ?? candidate.doi ?? candidate.core_id ?? `row-${index}`

/** Whether `candidate` is the paper `added` names: by openalex_id, else doi (any case), s2_id, arxiv_id or core_id. */
export function sameCandidate(candidate: Candidate, added: Candidate): boolean {
  if (added.openalex_id) return candidate.openalex_id === added.openalex_id
  if (added.doi) return candidate.doi?.toLowerCase() === added.doi.toLowerCase()
  if (added.s2_id) return candidate.s2_id === added.s2_id
  if (added.arxiv_id) return candidate.arxiv_id === added.arxiv_id
  if (added.core_id) return candidate.core_id === added.core_id
  return false
}
