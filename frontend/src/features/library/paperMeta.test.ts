import { describe, expect, it } from 'vitest'
import { byline, pageCountLabel, paperLabel, shortAuthors } from './paperMeta'

describe('shortAuthors', () => {
  it('lists up to two names, then "et al."', () => {
    expect(shortAuthors([])).toBe('')
    expect(shortAuthors(['Ada'])).toBe('Ada')
    expect(shortAuthors(['Ada', 'Alan'])).toBe('Ada, Alan')
    expect(shortAuthors(['Ada', 'Alan', 'Grace'])).toBe('Ada, Alan et al.')
  })
})

describe('pageCountLabel', () => {
  it('pluralises, and is empty before extraction has counted pages', () => {
    expect(pageCountLabel(1)).toBe('1 page')
    expect(pageCountLabel(12)).toBe('12 pages')
    expect(pageCountLabel(null)).toBe('')
  })
})

describe('byline', () => {
  it('joins authors, year and venue, leaving out what is missing', () => {
    expect(byline({ authors: ['Ada', 'Alan', 'Grace'], year: 2017, venue: 'NeurIPS' })).toBe(
      'Ada, Alan et al. · 2017 · NeurIPS',
    )
    expect(byline({ authors: [], year: 2017, venue: null })).toBe('2017')
    expect(byline({ authors: [], year: null, venue: null })).toBe('')
  })
})

describe('paperLabel', () => {
  it("names a paper by its first author's surname and year, or the surname alone without a year", () => {
    expect(paperLabel({ title: 'Dense Passage Retrieval', authors: ['Vladimir Karpukhin', 'Barlas Oğuz'], year: 2020 })).toBe(
      'Karpukhin 2020',
    )
    // Like the backend's source_label: a blank name is skipped, and a missing year keeps the author.
    expect(paperLabel({ title: 'Dense Passage Retrieval', authors: ['  ', 'Barlas Oğuz'], year: null })).toBe('Oğuz')
  })

  it('falls back to the title, cut to 24 characters, when no author name is known', () => {
    expect(paperLabel({ title: 'PaperLab E2E Fixture', authors: [], year: 2026 })).toBe('PaperLab E2E Fixture')
    expect(paperLabel({ title: 'PaperLab E2E Fixture With A Long Title', authors: ['  '], year: 2026 })).toBe(
      'PaperLab E2E Fixture Wi…',
    )
  })
})
