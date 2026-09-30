import { describe, expect, it } from 'vitest'
import { drawsPapers, PAPER_NODE_LIMIT, particlesFor } from './paperModel'

describe('drawsPapers', () => {
  it('draws each paper as a page up to the limit, and falls back to dots above it', () => {
    expect(drawsPapers(1)).toBe(true)
    expect(drawsPapers(PAPER_NODE_LIMIT)).toBe(true)
    expect(drawsPapers(PAPER_NODE_LIMIT + 1)).toBe(false)
  })
})

describe('particlesFor', () => {
  it('runs pulses along citations only', () => {
    expect(particlesFor('cites', false)).toBe(2)
    expect(particlesFor('similar', false)).toBe(0)
    expect(particlesFor('manual', false)).toBe(0)
  })

  it('stops the pulses on a citation faded out of focus', () => {
    expect(particlesFor('cites', true)).toBe(0)
  })
})
