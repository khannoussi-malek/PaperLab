import { describe, expect, it } from 'vitest'
import { byline, matchesPaper, pageCountLabel, paperLabel, shortAuthors } from './paperMeta'

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

describe('matchesPaper', () => {
  const paper = { title: 'Attention Is All You Need', authors: ['Ashish Vaswani', 'Jörg Müller'], year: 2017, venue: 'NeurIPS' }

  it('matches any word of the title, an author, the year or the venue, ignoring case and accents', () => {
    expect(matchesPaper(paper, 'attention')).toBe(true)
    expect(matchesPaper(paper, 'VASWANI')).toBe(true)
    expect(matchesPaper(paper, 'muller')).toBe(true)
    expect(matchesPaper(paper, '2017')).toBe(true)
    expect(matchesPaper(paper, 'neurips')).toBe(true)
    expect(matchesPaper(paper, 'transformer')).toBe(false)
  })

  it('needs every word of the query to match somewhere', () => {
    expect(matchesPaper(paper, 'vaswani 2017')).toBe(true)
    expect(matchesPaper(paper, 'vaswani 2018')).toBe(false)
  })

  it('matches the start of a word, not its middle, so a short query stays useful', () => {
    const bert = { title: 'BERT: Pre-training of Deep Bidirectional Transformers', authors: [], year: 2019, venue: null }
    expect(matchesPaper(bert, 'ai')).toBe(false)
    expect(matchesPaper(bert, 'train')).toBe(true)
    expect(matchesPaper(bert, 'pre-training')).toBe(true)
    expect(matchesPaper({ title: 'AI-Generated Code in the Wild', authors: [], year: null, venue: null }, 'ai')).toBe(true)
  })

  it('matches everything on a blank query, and a paper missing year and venue still matches its title', () => {
    expect(matchesPaper(paper, '   ')).toBe(true)
    expect(matchesPaper({ title: 'Untitled draft', authors: [], year: null, venue: null }, 'draft')).toBe(true)
  })
})
