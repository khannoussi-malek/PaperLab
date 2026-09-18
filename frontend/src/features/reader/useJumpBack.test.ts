import { describe, expect, it } from 'vitest'
import { afterScroll, type JumpSpot } from './useJumpBack'

describe('the way back from a citation jump (Q1-b)', () => {
  const spot: JumpSpot = { id: 1, scrollTop: 1000, page: 1, citationId: '38R', viaKeyboard: false, away: false }

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
