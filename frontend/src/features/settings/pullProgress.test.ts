import { describe, expect, it } from 'vitest'
import { describePull } from './pullProgress'

describe('describePull', () => {
  it('shows a whole percentage while sizes are known', () => {
    expect(describePull({ status: 'pulling 6a0746a1ec1a', total: 5_000, completed: 1_999 })).toEqual({
      label: 'pulling 6a0746a1ec1a · 39%',
      percent: 39,
    })
    expect(describePull({ status: 'pulling 6a07', total: 100, completed: 120 }).percent).toBe(100)
  })

  it('shows only the status before sizes are known, or when the total is zero', () => {
    expect(describePull({ status: 'pulling manifest', total: null, completed: null })).toEqual({ label: 'pulling manifest', percent: null })
    expect(describePull({ status: 'verifying sha256 digest', total: 0, completed: 0 }).percent).toBeNull()
  })
})
