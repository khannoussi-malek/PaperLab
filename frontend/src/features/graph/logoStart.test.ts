import { expect, it } from 'vitest'
import { MARK } from '@/features/scene3d/shape'
import { entranceScale, logoStart } from './logoStart'

type N = { id: string; x?: number; y?: number; z?: number }

it('places only the nodes with no position, on the logo outline at the given scale', () => {
  const nodes: N[] = [{ id: 'a' }, { id: 'b', x: 5, y: 6, z: 7 }, { id: 'c' }]
  const placed = logoStart(nodes, 10)
  expect(placed[1]).toEqual({ id: 'b', x: 5, y: 6, z: 7 })
  for (const n of [placed[0], placed[2]]) {
    expect(Math.abs(n.x!)).toBeLessThanOrEqual((MARK.w / 2) * 10 + 1e-9)
    expect(Math.abs(n.y!)).toBeLessThanOrEqual((MARK.h / 2) * 10 + 1e-9)
  }
  expect(nodes[0].x).toBeUndefined() // the input is never changed
  expect(logoStart(nodes, 10)).toEqual(placed) // the same every time
})

it('grows the logo with the graph, so a big library is not crammed', () => {
  expect(entranceScale(100)).toBeGreaterThan(entranceScale(10))
})
