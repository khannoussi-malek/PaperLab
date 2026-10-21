import { expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { detailsSourceLine, provenanceLines, sourceLabel } from './detailsSource'

const paper = (over: Partial<Paper>) => ({ field_sources: {}, manual_fields: [], ...over }) as unknown as Paper

it('labels a PDF-filled group "the PDF"', () => {
  expect(sourceLabel('pdf')).toBe('the PDF')
  expect(detailsSourceLine(paper({ details_source: 'openalex' }))).toBe('Details from OpenAlex')
})

it('"Details from" follows whichever source last wrote the title, authors and venue, else the creation source', () => {
  expect(detailsSourceLine(paper({ details_source: 'crossref', field_sources: { bibliographic: 'openalex' } }))).toBe(
    'Details from OpenAlex',
  )
  expect(detailsSourceLine(paper({ details_source: 'crossref' }))).toBe('Details from Crossref')
  expect(detailsSourceLine(paper({ details_source: 'crossref', field_sources: { bibliographic: 'manual' } }))).toBe(
    'Details edited by you',
  )
  expect(detailsSourceLine(paper({ details_source: null }))).toBeNull()
})

it('gives one line per group with a known source', () => {
  const lines = provenanceLines(paper({ field_sources: { bibliographic: 'openalex', abstract: 'pdf' } }))
  expect(lines).toEqual(['Title, authors and venue: from OpenAlex', 'Abstract: from the PDF'])
})

it('says "edited by you" for a group the owner corrected (source manual)', () => {
  const lines = provenanceLines(paper({ field_sources: { bibliographic: 'manual', identifiers: 'crossref' } }))
  expect(lines).toEqual(['Title, authors and venue: edited by you', 'Identifiers: from Crossref'])
})

it('never reads a lock the app set (manual_fields) as an edit: a saved search result keeps its source', () => {
  const lines = provenanceLines(paper({ field_sources: { bibliographic: 'crossref' }, manual_fields: ['title', 'doi'] }))
  expect(lines).toEqual(['Title, authors and venue: from Crossref'])
})

it('shows nothing for a group with neither', () => {
  expect(provenanceLines(paper({}))).toEqual([])
})
