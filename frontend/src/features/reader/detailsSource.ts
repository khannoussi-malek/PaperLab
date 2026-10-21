import type { Paper } from '@/api/client'

type FieldSource = Paper['field_sources'][string]

const DETAILS_SOURCE: Record<FieldSource, string> = {
  zotero: 'Zotero import',
  crossref: 'Crossref',
  openalex: 'OpenAlex',
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  search: 'a search result',
  manual: 'you',
  pdf: 'the PDF',
}

export const sourceLabel = (source: FieldSource): string => DETAILS_SOURCE[source]

/** "Details from Crossref": where a paper's title, authors and abstract came from, or null when that isn't known. */
export const detailsSourceLine = (paper: Pick<Paper, 'details_source'>): string | null =>
  paper.details_source ? `Details from ${DETAILS_SOURCE[paper.details_source]}` : null

/** Each group of details, its readable name, and the fields in it. Mirrors FIELD_GROUPS in backend/app/core/provenance.py. */
const GROUPS: readonly { key: string; name: string; fields: readonly string[] }[] = [
  { key: 'bibliographic', name: 'Title, authors and venue', fields: ['title', 'authors', 'year', 'venue', 'issn', 'type'] },
  { key: 'identifiers', name: 'Identifiers', fields: ['doi', 'openalex_id', 'pmid', 'pmcid'] },
  { key: 'citation', name: 'Volume, issue and pages', fields: ['volume', 'issue', 'pages', 'editors'] },
  { key: 'abstract', name: 'Abstract', fields: ['abstract'] },
  { key: 'source_type', name: 'Source type', fields: ['source_type', 'peer_reviewed'] },
  { key: 'published', name: 'Published version', fields: ['published_doi', 'published_venue'] },
]

/** "Abstract: from the PDF" per group; "edited by you" wins over a source, and a group with neither is left out. */
export function provenanceLines(paper: Pick<Paper, 'field_sources' | 'manual_fields'>): string[] {
  return GROUPS.flatMap(({ key, name, fields }) => {
    if (fields.some((f) => paper.manual_fields.includes(f))) return [`${name}: edited by you`]
    const source = paper.field_sources[key]
    return source ? [`${name}: from ${DETAILS_SOURCE[source]}`] : []
  })
}
