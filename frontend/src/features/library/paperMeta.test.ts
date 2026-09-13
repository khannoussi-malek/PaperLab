import { describe, expect, it } from 'vitest'
import { authorNames, byline, pageCountLabel, shortAuthors } from './paperMeta'

describe('authorNames', () => {
  it('reads plain strings and {name} / {display_name} objects, skipping anything else', () => {
    expect(authorNames(['Ada Lovelace', { name: 'Alan Turing' }, { display_name: 'Grace Hopper' }])).toEqual([
      'Ada Lovelace',
      'Alan Turing',
      'Grace Hopper',
    ])
    expect(authorNames([null, 42, { id: 'A1' }, '  ', { name: '' }])).toEqual([])
  })
})

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
