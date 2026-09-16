import { describe, expect, it } from 'vitest'
import type { Candidate } from '@/api/client'
import { candidateKey, citationsLabel, pageLink } from './candidateMeta'

const ids = { doi: null, arxiv_id: null, openalex_id: null, s2_id: null }

describe('pageLink', () => {
  it('prefers the DOI, then arXiv, then OpenAlex, then Semantic Scholar', () => {
    const all = { doi: '10.1/x', arxiv_id: '1810.04805', openalex_id: 'W1', s2_id: 'a'.repeat(40) }
    expect(pageLink(all)).toBe('https://doi.org/10.1/x')
    expect(pageLink({ ...all, doi: null })).toBe('https://arxiv.org/abs/1810.04805')
    expect(pageLink({ ...all, doi: null, arxiv_id: null })).toBe('https://openalex.org/W1')
    expect(pageLink({ ...ids, s2_id: 'a'.repeat(40) })).toBe(`https://www.semanticscholar.org/paper/${'a'.repeat(40)}`)
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
    expect(candidateKey(candidate({}), 3)).toBe('row-3')
  })
})
