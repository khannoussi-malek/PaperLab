import { describe, expect, it } from 'vitest'
import type { Candidate } from '@/api/client'
import { candidateKey, citationsLabel, pageLink, sameCandidate } from './candidateMeta'

const ids = { doi: null, external_ids: {} }

describe('pageLink', () => {
  it('prefers the DOI, then arXiv, then OpenAlex, then Semantic Scholar, then CORE', () => {
    const all = { doi: '10.1/x', external_ids: { arxiv: '1810.04805', openalex: 'W1', semantic_scholar: 'a'.repeat(40), core: '42' } }
    expect(pageLink(all)).toBe('https://doi.org/10.1/x')
    expect(pageLink({ ...all, doi: null })).toBe('https://arxiv.org/abs/1810.04805')
    expect(pageLink({ ...all, doi: null, external_ids: { ...all.external_ids, arxiv: undefined as unknown as string } })).toBe(
      'https://openalex.org/W1',
    )
    expect(pageLink({ ...ids, external_ids: { semantic_scholar: 'a'.repeat(40), core: '42' } })).toBe(
      `https://www.semanticscholar.org/paper/${'a'.repeat(40)}`,
    )
    expect(pageLink({ ...ids, external_ids: { core: '42' } })).toBe('https://core.ac.uk/works/42')
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
  it('uses the first identifier, else the doi, else the position', () => {
    const candidate = (fields: Partial<Candidate>) => ({ ...ids, ...fields }) as Candidate
    expect(candidateKey(candidate({ external_ids: { openalex: 'W1' }, doi: '10.1/x' }), 0)).toBe('W1')
    expect(candidateKey(candidate({ doi: '10.1/x' }), 0)).toBe('10.1/x')
    expect(candidateKey(candidate({ external_ids: { core: '42' } }), 0)).toBe('42')
    expect(candidateKey(candidate({}), 3)).toBe('row-3')
  })
})

describe('sameCandidate', () => {
  const candidate = (fields: Partial<Candidate>) => ({ ...ids, title: 'T', ...fields }) as Candidate

  it('matches by openalex id, else doi in any case, else semantic_scholar, arxiv or core', () => {
    expect(
      sameCandidate(
        candidate({ external_ids: { openalex: 'W1' } }),
        candidate({ external_ids: { openalex: 'W1' }, doi: '10.1/other' }),
      ),
    ).toBe(true)
    expect(
      sameCandidate(candidate({ external_ids: { openalex: 'W2' } }), candidate({ external_ids: { openalex: 'W1' } })),
    ).toBe(false)
    expect(sameCandidate(candidate({ doi: '10.1/X' }), candidate({ doi: '10.1/x' }))).toBe(true)
    expect(
      sameCandidate(
        candidate({ external_ids: { semantic_scholar: 'a'.repeat(40) } }),
        candidate({ external_ids: { semantic_scholar: 'a'.repeat(40) } }),
      ),
    ).toBe(true)
    // arXiv and CORE find papers that have no other identifier.
    expect(
      sameCandidate(
        candidate({ external_ids: { arxiv: '2609.00001' } }),
        candidate({ external_ids: { arxiv: '2609.00001' } }),
      ),
    ).toBe(true)
    expect(sameCandidate(candidate({ external_ids: { core: '42' } }), candidate({ external_ids: { core: '42' } }))).toBe(true)
    expect(sameCandidate(candidate({ external_ids: { core: '43' } }), candidate({ external_ids: { core: '42' } }))).toBe(false)
  })

  it('is false when the added candidate has no identifier to match on', () => {
    expect(sameCandidate(candidate({ external_ids: { openalex: 'W1' } }), candidate({}))).toBe(false)
  })
})
