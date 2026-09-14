import { describe, expect, it } from 'vitest'
import { isFresh } from './motion'

describe('isFresh', () => {
  const now = Date.parse('2026-09-14T12:00:10Z')

  it('is true for something created in the last few seconds, so it animates in once', () => {
    expect(isFresh('2026-09-14T12:00:08Z', now)).toBe(true)
  })

  it('is false for something loaded from earlier, so a reload or a filter change stays still', () => {
    expect(isFresh('2026-09-14T11:59:00Z', now)).toBe(false)
    expect(isFresh('2026-01-01T00:00:00Z', now)).toBe(false)
  })

  it('is false for a timestamp it cannot read', () => {
    expect(isFresh('not a date', now)).toBe(false)
  })
})
