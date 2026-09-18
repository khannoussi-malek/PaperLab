import type { GraphLink, GraphNode } from '@/api/client'
import { byFirstWorkspace, degrees, hopDistances, MAX_HOPS } from './graphModel'

export const RINGS_HINT = 'Centred on the most connected paper. Choose a paper to centre on it.'

/** Where papers further than MAX_HOPS links from the centre, or not connected to it at all, sit. */
export const OUTER_RING = MAX_HOPS + 1

/** A paper's ring and its place, in ring-widths from the centre: the canvas scales a ring-width to its box. */
export type RingPlace = { ring: number; x: number; y: number }

/** D116: the focused paper when it is on screen, else the most connected (visible links, then title). */
export function ringsCentre(nodes: GraphNode[], links: GraphLink[], focusId: string | null): string | null {
  if (focusId !== null && nodes.some((node) => node.id === focusId)) return focusId
  const degree = degrees(links)
  const count = (node: GraphNode) => degree.get(node.id) ?? 0
  const [busiest] = [...nodes].sort((a, b) => count(b) - count(a) || a.title.localeCompare(b.title))
  return busiest?.id ?? null
}

/**
 * Every paper pinned to the ring of its hop distance from the centre (1 to MAX_HOPS; OUTER_RING beyond that or
 * unconnected). A ring's papers spread evenly by angle, clockwise from the top, sorted by first workspace (unfiled
 * last) then title, so a project sits together.
 */
export function ringsLayout(nodes: GraphNode[], links: GraphLink[], centre: string): Map<string, RingPlace> {
  const distance = hopDistances(links, centre, MAX_HOPS)
  const rings = Array.from({ length: OUTER_RING }, (_, index) =>
    nodes
      .filter((node) => node.id !== centre && (distance.get(node.id) ?? OUTER_RING) === index + 1)
      .sort((a, b) => byFirstWorkspace(a, b) || a.title.localeCompare(b.title))
  )
  const placed = rings.flatMap((papers, index) =>
    papers.map((node, slot): [string, RingPlace] => {
      const ring = index + 1
      const angle = -Math.PI / 2 + (2 * Math.PI * slot) / papers.length
      return [node.id, { ring, x: ring * Math.cos(angle), y: ring * Math.sin(angle) }]
    })
  )
  return new Map([[centre, { ring: 0, x: 0, y: 0 }], ...placed])
}
