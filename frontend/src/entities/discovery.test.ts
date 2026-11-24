import { describe, expect, it } from 'vitest'
import { sameCandidate, type Candidate } from './discovery'

const ids = { doi: null, external_ids: {} }

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

  it('matches by doi even when added also carries a semantic_scholar id the other row lacks', () => {
    // Pins doi ranking second (right after openalex), not last: a row that never got an S2 match must still
    // dedup against one that did, as long as they share a doi — otherwise the UI shows a stale "Add" button.
    expect(
      sameCandidate(
        candidate({ doi: '10.1/x' }),
        candidate({ doi: '10.1/x', external_ids: { semantic_scholar: 'a'.repeat(40) } }),
      ),
    ).toBe(true)
  })

  it('is false when the added candidate has no identifier to match on', () => {
    expect(sameCandidate(candidate({ external_ids: { openalex: 'W1' } }), candidate({}))).toBe(false)
  })

  it('matches by pubmed id when nothing stronger is set', () => {
    expect(
      sameCandidate(candidate({ external_ids: { pubmed: '42825172' } }), candidate({ external_ids: { pubmed: '42825172' } })),
    ).toBe(true)
    expect(
      sameCandidate(candidate({ external_ids: { pubmed: '1' } }), candidate({ external_ids: { pubmed: '2' } })),
    ).toBe(false)
  })

  it('matches by pmc id when nothing stronger is set', () => {
    expect(
      sameCandidate(candidate({ external_ids: { pmc: '9876543' } }), candidate({ external_ids: { pmc: '9876543' } })),
    ).toBe(true)
    expect(
      sameCandidate(candidate({ external_ids: { pmc: '1' } }), candidate({ external_ids: { pmc: '2' } })),
    ).toBe(false)
  })

  it('matches by zenodo id when nothing stronger is set', () => {
    expect(
      sameCandidate(candidate({ external_ids: { zenodo: '123456' } }), candidate({ external_ids: { zenodo: '123456' } })),
    ).toBe(true)
    expect(
      sameCandidate(candidate({ external_ids: { zenodo: '1' } }), candidate({ external_ids: { zenodo: '2' } })),
    ).toBe(false)
  })
})
