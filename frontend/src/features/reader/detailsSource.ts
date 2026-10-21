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

/** "Details from Crossref": the source that last wrote the title, authors and venue, else the one the paper was created
 * from; "Details edited by you" after the owner corrected them; null when neither is known. */
export function detailsSourceLine(paper: Pick<Paper, 'details_source' | 'field_sources'>): string | null {
  const latest = paper.field_sources.bibliographic
  if (latest === 'manual') return 'Details edited by you'
  const source = latest ?? paper.details_source
  return source ? `Details from ${DETAILS_SOURCE[source]}` : null
}

/** Each group of details, its readable name, and the fields in it. Mirrors FIELD_GROUPS in backend/app/core/provenance.py. */
const GROUPS: readonly { key: string; name: string; fields: readonly string[] }[] = [
  { key: 'bibliographic', name: 'Title, authors and venue', fields: ['title', 'authors', 'year', 'venue', 'issn', 'type'] },
  { key: 'identifiers', name: 'Identifiers', fields: ['doi', 'openalex_id', 'pmid', 'pmcid'] },
  { key: 'citation', name: 'Volume, issue and pages', fields: ['volume', 'issue', 'pages', 'editors'] },
  { key: 'abstract', name: 'Abstract', fields: ['abstract'] },
  { key: 'source_type', name: 'Source type', fields: ['source_type', 'peer_reviewed'] },
  { key: 'published', name: 'Published version', fields: ['published_doi', 'published_venue'] },
]

/** "Abstract: from the PDF" per group, "edited by you" for a group the owner corrected (its source is `manual`), and
 * nothing for a group with no known source. Never read from manual_fields: it also holds locks the app sets itself. */
export function provenanceLines(paper: Pick<Paper, 'field_sources'>): string[] {
  return GROUPS.flatMap(({ key, name }) => {
    const source = paper.field_sources[key]
    if (!source) return []
    return [source === 'manual' ? `${name}: edited by you` : `${name}: from ${DETAILS_SOURCE[source]}`]
  })
}
