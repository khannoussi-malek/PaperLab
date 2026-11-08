import { COL, type Box, type Layout } from './layout'

export const RING = 90
const ROOT_ORBIT = 18 // several search roots share the centre on a small circle, inside radius 30

export type RadialBox = { box: Box; angle: number; radius: number; x: number; y: number }

/** Wraps the tidy tree around a centre: y becomes the angle, the level column becomes the ring. */
export function toRadial(layout: Layout): RadialBox[] {
  const roots = layout.boxes.filter((b) => b.root).length
  return layout.boxes.map((box) => {
    const angle = (box.y / layout.height) * 2 * Math.PI
    const radius = box.root ? (roots > 1 ? ROOT_ORBIT : 0) : Math.round(box.x / COL) * RING
    return { box, angle, radius, x: radius * Math.cos(angle), y: radius * Math.sin(angle) }
  })
}
