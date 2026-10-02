import { seeded } from '@/features/scene3d/clock'
import { markPoints } from '@/features/scene3d/shape'

/**
 * The 3D graph's entrance: papers with no position yet start on the PaperLab logo's outline, and the force
 * simulation springs them out into the real layout. Papers that already have a position (carried over from the
 * last layout) are left where they are, so a rebuild never replays it. Never changes `nodes`.
 */
export function logoStart<T extends { x?: number }>(nodes: T[], scale: number): T[] {
  const points = markPoints(nodes.length, seeded(7))
  return nodes.map((node, i) => {
    if (node.x !== undefined) return node
    const [x, y, z] = points[i]
    return { ...node, x: x * scale, y: y * scale, z: z * scale }
  })
}

/** World units per logo unit: the logo grows with the graph. */
export const entranceScale = (count: number) => 12 + 3 * Math.sqrt(count)
