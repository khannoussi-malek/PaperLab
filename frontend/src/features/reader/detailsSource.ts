import type { Paper } from '@/api/client'

const DETAILS_SOURCE: Record<NonNullable<Paper['details_source']>, string> = {
  zotero: 'Zotero import',
  crossref: 'Crossref',
  openalex: 'OpenAlex',
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  search: 'a search result',
  manual: 'you',
}

/** "Details from Crossref": where a paper's title, authors and abstract came from, or null when that isn't known. */
export const detailsSourceLine = (paper: Pick<Paper, 'details_source'>): string | null =>
  paper.details_source ? `Details from ${DETAILS_SOURCE[paper.details_source]}` : null
