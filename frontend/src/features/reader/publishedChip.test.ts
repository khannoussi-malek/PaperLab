import { describe, expect, it } from 'vitest'
import { publishedChipText, venueShort } from './publishedChip'

describe('venueShort', () => {
  it('takes an acronym-shaped closing parenthetical', () => {
    expect(venueShort('Symposium on Theory of Computing (STOC)')).toBe('STOC')
    expect(venueShort('International Conference on Learning Representations (ICLR 2025)')).toBe('ICLR 2025')
  })
  it('ignores a parenthetical that is not an acronym', () => {
    expect(venueShort('Proceedings of the ACL (Long and Short Papers)')).toBe('ACL (Long and Short Papers)')
    expect(venueShort('Nature Communications (Print)')).toBe('Nature Communications (Print)')
  })
  it('drops the proceedings boilerplate and a leading year, not the length', () => {
    expect(venueShort('Proceedings of the 57th Annual Symposium on Theory')).toBe('Symposium on Theory')
    expect(venueShort('2025 Conference on Empirical Methods in Natural Language Processing')).toBe(
      'Conference on Empirical Methods in Natural Language Processing',
    )
  })
})

describe('publishedChipText', () => {
  it('reads "Published: venue year"', () => {
    expect(publishedChipText('Proceedings (STOC)', 2025)).toBe('Published: STOC 2025')
    expect(publishedChipText(null, 2025)).toBe('Published: 2025')
    expect(publishedChipText('Nature', null)).toBe('Published: Nature')
  })
})
