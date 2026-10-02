import { expect, it } from 'vitest'
import { seeded } from './clock'
import { MARK, markPoints } from './shape'

it('puts every point on the logo card, the same points for the same seed', () => {
  const points = markPoints(500, seeded(7))
  expect(points).toHaveLength(500)
  for (const [x, y] of points) {
    expect(Math.abs(x)).toBeLessThanOrEqual(MARK.w / 2 + 1e-9)
    expect(Math.abs(y)).toBeLessThanOrEqual(MARK.h / 2 + 1e-9)
  }
  expect(markPoints(5, seeded(7))).toEqual(markPoints(5, seeded(7)))
})
