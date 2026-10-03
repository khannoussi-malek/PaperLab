import { describe, expect, it } from 'vitest'
import { INTRO_FORMED, approach, clamp01, intro, progress, seeded, sheenEvery } from './clock'

describe('clock', () => {
  it('clamps to 0..1, and treats NaN as 0', () => {
    expect([clamp01(-1), clamp01(0.4), clamp01(3), clamp01(Number.NaN)]).toEqual([0, 0.4, 1, 0])
    expect(progress(2, 1, 2)).toBe(0.5)
  })

  it('runs the intro in order: dust gathers, then the card shows, then the highlighter sweeps', () => {
    expect(intro(0)).toMatchObject({ gather: 0, card: 0, sweep: 0, swarm: 1 })
    expect(intro(1.7).gather).toBeGreaterThan(0.5)
    expect(intro(1.7).card).toBe(0)
    expect(intro(2.3).sweep).toBe(0)
    expect(intro(INTRO_FORMED)).toMatchObject({ gather: 1, card: 1, sweep: 1, flash: expect.closeTo(0, 9), swarm: 0.75 })
  })

  it('eases toward a target at the same rate per second whatever the frame rate, never past it', () => {
    let fast = 0
    for (let i = 0; i < 60; i++) fast = approach(fast, 1, 1 / 60)
    let slow = 0
    for (let i = 0; i < 20; i++) slow = approach(slow, 1, 1 / 20)
    expect(fast).toBeCloseTo(slow, 6)
    expect(fast).toBeLessThan(1)
    expect(approach(0.5, 0.5, 1)).toBe(0.5) // a held target holds
  })

  it('crosses the sheen once every period, off the page between crossings', () => {
    expect(sheenEvery(0.5)).toBe(0)
    expect(sheenEvery(5.3)).toBeCloseTo(0.5, 9)
    expect(sheenEvery(11.3)).toBeCloseTo(sheenEvery(5.3), 9)
  })

  it('draws the same random sequence for the same seed', () => {
    const a = seeded(7)
    const b = seeded(7)
    expect([a(), a(), a()]).toEqual([b(), b(), b()])
  })
})
