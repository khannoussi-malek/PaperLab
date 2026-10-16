import { describe, expect, it } from 'vitest'
import { publishedChipText, venueShort } from './publishedChip'

describe('venueShort', () => {
  it('takes the closing parenthetical', () => {
    expect(venueShort('Symposium on Theory of Computing (STOC)')).toBe('STOC')
  })
  it('cuts a venue without one at 40 characters', () => {
    expect(venueShort('Conference on Empirical Methods in Natural Language Processing')).toBe(
      'Conference on Empirical Methods in Natur…',
    )
    expect(venueShort('Nature')).toBe('Nature')
  })
})

describe('publishedChipText', () => {
  it('reads "Published: venue year"', () => {
    expect(publishedChipText('Proceedings (STOC)', 2025)).toBe('Published: STOC 2025')
    expect(publishedChipText(null, 2025)).toBe('Published: 2025')
    expect(publishedChipText('Nature', null)).toBe('Published: Nature')
  })
})
