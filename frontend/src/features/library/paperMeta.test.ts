import { describe, expect, it } from 'vitest'
import { byline, pageCountLabel, shortAuthors } from './paperMeta'

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
