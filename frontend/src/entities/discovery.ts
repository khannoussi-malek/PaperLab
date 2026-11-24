import type { components } from './schema'

export type NoveltyResult = components['schemas']['NoveltyOut']
export type Candidate = components['schemas']['CandidateOut']
export type SearchResult = components['schemas']['SearchOut']

/** Whether `candidate` is the paper `added` names: by openalex id, else doi (any case), semantic_scholar, arxiv,
 * core, pubmed, pmc, zenodo, hal, doaj, openaire, iacr_eprint, biorxiv or medrxiv. Doi ranks second here (not last, unlike candidateKey/pageLink) because this drives "already in your
 * library" dedup across cached search results — ranking it last reintroduced a real gap: two rows for the same
 * paper that share a doi but not a semantic_scholar id (e.g. one row never got an S2 match) would stop matching,
 * leaving a stale "Add" button that 409s on click. */
export function sameCandidate(candidate: Candidate, added: Candidate): boolean {
  if (added.external_ids.openalex) return candidate.external_ids.openalex === added.external_ids.openalex
  if (added.doi) return candidate.doi?.toLowerCase() === added.doi.toLowerCase()
  for (const source of ['semantic_scholar', 'arxiv', 'core', 'pubmed', 'pmc', 'zenodo', 'hal', 'doaj', 'openaire', 'iacr_eprint', 'biorxiv', 'medrxiv', 'dblp', 'openreview', 'acl_anthology']) {
    const addedId = added.external_ids[source]
    if (addedId) return candidate.external_ids[source] === addedId
  }
  return false
}
