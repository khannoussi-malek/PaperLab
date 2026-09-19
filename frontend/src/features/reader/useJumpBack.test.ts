import { describe, expect, it } from 'vitest'
import { afterScroll, forScale, type JumpSpot } from './useJumpBack'

describe('the way back from a citation jump (Q1-b)', () => {
  const spot: JumpSpot = { id: 1, scrollTop: 1000, page: 1, citationId: '38R', viaKeyboard: false, away: false, scale: 1 }

  it('stays while the jump is still near the spot, and arms once it is half a screen away', () => {
    expect(afterScroll(spot, 1200, 800)).toBe(spot)
    expect(afterScroll(spot, 1400, 800)).toEqual({ ...spot, away: true })
  })

  it('stays while the reader is elsewhere, and goes once they scroll back within half a screen by hand', () => {
    const away = { ...spot, away: true }
    expect(afterScroll(away, 3000, 800)).toBe(away)
    expect(afterScroll(away, 1399, 800)).toBeNull()
    expect(afterScroll(away, 601, 800)).toBeNull()
  })
})

describe('forScale (a zoom change invalidates the saved scroll offset)', () => {
  const spot: JumpSpot = { id: 1, scrollTop: 1000, page: 1, citationId: '38R', viaKeyboard: false, away: false, scale: 1 }

  it('keeps a spot saved at this scale, and drops it once the reader has zoomed to a different one', () => {
    expect(forScale(spot, 1)).toBe(spot)
    expect(forScale(spot, 1.5)).toBeNull()
  })

  it('passes an already-cleared spot through as null', () => {
    expect(forScale(null, 1)).toBeNull()
  })
})
