import { COL, type Box, type Layout } from './layout'

export const RING = 120
export const ROOT_RING = 40 // several search roots sit on this small inner ring; a lone one sits at the centre
export const MIN_SECTOR = 6 // degrees every search root gets, however few papers it holds

export type RadialBox = { box: Box; angle: number; radius: number; x: number; y: number; sector: [number, number] }

/**
 * Wraps the tidy tree around a centre. Each search root owns a sector of the circle, proportional to the drawn papers
 * under it (at least MIN_SECTOR degrees); inside it papers spread by leaf order, parents centred on their children.
 */
export function toRadial(layout: Layout): RadialBox[] {
  const kids = new Map<string, string[]>()
  const hasParent = new Set<string>()
  for (const e of layout.edges) {
    kids.set(e.from, [...(kids.get(e.from) ?? []), e.to])
    hasParent.add(e.to)
  }
  const byId = new Map(layout.boxes.map((b) => [b.id, b]))
  const leaves = new Map<string, number>()
  const count = (id: string): number => {
    const k = kids.get(id) ?? []
    const n = k.length ? k.reduce((s, c) => s + count(c), 0) : 1
    leaves.set(id, n)
    return n
  }
  const tops = layout.boxes.filter((b) => !hasParent.has(b.id))
  tops.forEach((t) => count(t.id))

  // sqrt of the papers underneath: small searches get room, the big one still reads as biggest
  const weight = (id: string) => Math.sqrt(leaves.get(id)!)
  const total = tops.reduce((s, t) => s + weight(t.id), 0)
  const full = 2 * Math.PI
  const min = (MIN_SECTOR * Math.PI) / 180
  const small = tops.filter((t) => (weight(t.id) / total) * full < min)
  const rest = total - small.reduce((s, t) => s + weight(t.id), 0)
  const room = full - small.length * min
  const width = (id: string) => (small.some((t) => t.id === id) ? min : (weight(id) / rest) * room)

  const out = new Map<string, RadialBox>()
  const rootCount = layout.boxes.filter((b) => b.root).length
  const place = (id: string, a0: number, a1: number) => {
    const box = byId.get(id)!
    const angle = (a0 + a1) / 2
    const radius = box.root ? (rootCount > 1 ? ROOT_RING : 0) : Math.round(box.x / COL) * RING
    out.set(id, { box, angle, radius, x: radius * Math.cos(angle), y: radius * Math.sin(angle), sector: [a0, a1] })
    const k = kids.get(id) ?? []
    const sum = k.reduce((s, c) => s + weight(c), 0)
    let at = a0
    for (const c of k) {
      const w = ((a1 - a0) * weight(c)) / sum
      place(c, at, at + w)
      at += w
    }
  }
  let start = -Math.PI / 2
  for (const t of tops) {
    const w = width(t.id)
    place(t.id, start, start + w)
    start += w
  }
  return layout.boxes.map((b) => out.get(b.id)!)
}
