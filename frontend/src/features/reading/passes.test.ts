import { describe, expect, it } from 'vitest'
import { nextPass, PASSES, readingChip } from './passes'

describe('PASSES', () => {
  it('has three passes, with Keshav 2007’s headings', () => {
    expect(PASSES.map((pass) => pass.heading)).toEqual(['Pass 1 · 5–10 minutes', 'Pass 2 · about an hour', 'Pass 3 · 1–5 hours'])
  })
})

describe('nextPass', () => {
  it('gives the next pass for 0–2, and none once every pass is finished', () => {
    expect([0, 1, 2].map(nextPass)).toEqual([PASSES[0], PASSES[1], PASSES[2]])
    expect(nextPass(3)).toBeNull()
  })
})

describe('readingChip', () => {
  it('is null at the normal state, and otherwise names the level, the decision, or both', () => {
    expect(readingChip(0, null)).toBeNull()
    expect(readingChip(0, 'later')).toBe('Later')
    expect(readingChip(0, 'drop')).toBe('Dropped')
    expect(readingChip(2, null)).toBe('Pass 2')
    expect(readingChip(2, 'later')).toBe('Pass 2 · Later')
  })
})
