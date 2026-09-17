import { describe, expect, it } from 'vitest'
import type { Candidate } from '@/api/client'
import { candidateKey, citationsLabel, pageLink, sameCandidate } from './candidateMeta'

const ids = { doi: null, arxiv_id: null, openalex_id: null, s2_id: null, core_id: null }

describe('pageLink', () => {
  it('prefers the DOI, then arXiv, then OpenAlex, then Semantic Scholar, then CORE', () => {
    const all = { doi: '10.1/x', arxiv_id: '1810.04805', openalex_id: 'W1', s2_id: 'a'.repeat(40), core_id: '42' }
    expect(pageLink(all)).toBe('https://doi.org/10.1/x')
    expect(pageLink({ ...all, doi: null })).toBe('https://arxiv.org/abs/1810.04805')
    expect(pageLink({ ...all, doi: null, arxiv_id: null })).toBe('https://openalex.org/W1')
    expect(pageLink({ ...ids, s2_id: 'a'.repeat(40), core_id: '42' })).toBe(
      `https://www.semanticscholar.org/paper/${'a'.repeat(40)}`,
    )
    expect(pageLink({ ...ids, core_id: '42' })).toBe('https://core.ac.uk/works/42')
  })

  it('is null without any identifier', () => {
    expect(pageLink(ids)).toBeNull()
  })
})

describe('citationsLabel', () => {
  it('groups thousands and says citation for one', () => {
    expect(citationsLabel(120985)).toBe('120,985 citations')
    expect(citationsLabel(1)).toBe('1 citation')
    expect(citationsLabel(0)).toBe('0 citations')
  })

  it('is empty when the count is unknown', () => {
    expect(citationsLabel(null)).toBe('')
  })
})

describe('candidateKey', () => {
  it('uses the first identifier, else the position', () => {
    const candidate = (fields: Partial<Candidate>) => ({ ...ids, ...fields }) as Candidate
    expect(candidateKey(candidate({ openalex_id: 'W1', doi: '10.1/x' }), 0)).toBe('W1')
    expect(candidateKey(candidate({ doi: '10.1/x' }), 0)).toBe('10.1/x')
    expect(candidateKey(candidate({ core_id: '42' }), 0)).toBe('42')
    expect(candidateKey(candidate({}), 3)).toBe('row-3')
  })
})

describe('sameCandidate', () => {
  const candidate = (fields: Partial<Candidate>) => ({ ...ids, title: 'T', ...fields }) as Candidate

  it('matches by openalex_id, else doi in any case, else s2_id, arxiv_id or core_id', () => {
    expect(sameCandidate(candidate({ openalex_id: 'W1' }), candidate({ openalex_id: 'W1', doi: '10.1/other' }))).toBe(
      true,
    )
    expect(sameCandidate(candidate({ openalex_id: 'W2' }), candidate({ openalex_id: 'W1' }))).toBe(false)
    expect(sameCandidate(candidate({ doi: '10.1/X' }), candidate({ doi: '10.1/x' }))).toBe(true)
    expect(sameCandidate(candidate({ s2_id: 'a'.repeat(40) }), candidate({ s2_id: 'a'.repeat(40) }))).toBe(true)
    // arXiv and CORE find papers that have no other identifier.
    expect(sameCandidate(candidate({ arxiv_id: '2609.00001' }), candidate({ arxiv_id: '2609.00001' }))).toBe(true)
    expect(sameCandidate(candidate({ core_id: '42' }), candidate({ core_id: '42' }))).toBe(true)
    expect(sameCandidate(candidate({ core_id: '43' }), candidate({ core_id: '42' }))).toBe(false)
  })

  it('is false when the added candidate has no identifier to match on', () => {
    expect(sameCandidate(candidate({ openalex_id: 'W1' }), candidate({}))).toBe(false)
  })
})
