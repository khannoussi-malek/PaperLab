import { expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { detailsSourceLine, provenanceLines, sourceLabel } from './detailsSource'

const paper = (over: Partial<Paper>) => ({ field_sources: {}, manual_fields: [], ...over }) as unknown as Paper

it('labels a PDF-filled group "the PDF"', () => {
  expect(sourceLabel('pdf')).toBe('the PDF')
  expect(detailsSourceLine({ details_source: 'openalex' })).toBe('Details from OpenAlex')
})

it('gives one line per group with a known source', () => {
  const lines = provenanceLines(paper({ field_sources: { bibliographic: 'openalex', abstract: 'pdf' } }))
  expect(lines).toEqual(['Title, authors and venue: from OpenAlex', 'Abstract: from the PDF'])
})

it('says "edited by you" when a manual field is in the group, and that wins over a source', () => {
  const lines = provenanceLines(paper({ field_sources: { bibliographic: 'openalex' }, manual_fields: ['year', 'doi'] }))
  expect(lines).toEqual(['Title, authors and venue: edited by you', 'Identifiers: edited by you'])
})

it('shows nothing for a group with neither', () => {
  expect(provenanceLines(paper({}))).toEqual([])
})
