import { describe, expect, it } from 'vitest'
import type { GraphLink, GraphNode } from '@/api/client'
import { OUTER_RING, RINGS_HINT, ringsCentre, ringsLayout } from './ringsModel'

const link = (source: string, target: string, kind: GraphLink['kind'] = 'similar'): GraphLink => ({
  source,
  target,
  kind,
  id: null,
  label: null,
})

const node = (id: string, title = id.toUpperCase(), workspaces: string[] = []): GraphNode => ({
  id,
  title,
  year: null,
  workspaces,
  has_notes: false,
  status: 'ready',
  added_at: '2026-09-13T10:00:00Z',
})

// c is the hub: a–c, b–c, c–d, then a chain d–e–f; g is alone.
const nodes = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((id) => node(id))
const links = [link('a', 'c', 'cites'), link('b', 'c'), link('c', 'd'), link('d', 'e', 'manual'), link('e', 'f')]

describe('the rings’ centre', () => {
  it('is the focused paper, or else the most connected one', () => {
    expect(ringsCentre(nodes, links, 'e')).toBe('e')
    expect(ringsCentre(nodes, links, null)).toBe('c')
    // A focus that is not on screen (it was another workspace's paper) falls back too.
    expect(ringsCentre(nodes, links, 'elsewhere')).toBe('c')
    expect(ringsCentre([], [], null)).toBeNull()
    expect(RINGS_HINT).toBe('Centred on the most connected paper. Choose a paper to centre on it.')
  })

  it('breaks a tie for most connected by title', () => {
    expect(ringsCentre([node('z', 'Zeta'), node('y', 'Alpha')], [link('z', 'y')], null)).toBe('y')
  })
})

describe('the rings', () => {
  it('put each paper on the ring of its hop distance, and the far and the unconnected on the outer ring', () => {
    const places = ringsLayout(nodes, links, 'a')
    expect(Object.fromEntries([...places].map(([id, place]) => [id, place.ring]))).toEqual({
      a: 0,
      c: 1,
      b: 2,
      d: 2,
      e: 3,
      f: 4,
      g: 4,
    })
    expect(OUTER_RING).toBe(4)
    expect(places.get('a')).toEqual({ ring: 0, x: 0, y: 0 })
    // Ring k sits k ring-widths from the centre; the canvas scales a ring-width to its box.
    for (const [id, place] of places) expect(Math.hypot(place.x, place.y), id).toBeCloseTo(place.ring)
  })

  it('spread a ring evenly from the top, clockwise, by first workspace (unfiled last) then title', () => {
    const ring = [
      node('hub', 'Hub'),
      node('u', 'Unfiled'),
      node('t', 'Beta', ['Thesis']),
      node('r2', 'Zulu', ['Reading']),
      node('r1', 'Alpha', ['Reading']),
    ]
    const places = ringsLayout(ring, ring.slice(1).map((paper) => link('hub', paper.id)), 'hub')
    const angle = (id: string) => {
      const place = places.get(id)
      return Math.atan2(place?.y ?? 0, place?.x ?? 0)
    }
    // A quarter turn apart from the top (y grows downwards on the canvas): Reading's two, then Thesis, then unfiled.
    expect(angle('r1')).toBeCloseTo(-Math.PI / 2)
    expect(angle('r2')).toBeCloseTo(0)
    expect(angle('t')).toBeCloseTo(Math.PI / 2)
    expect(Math.abs(angle('u'))).toBeCloseTo(Math.PI)
  })
})
