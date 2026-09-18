import { describe, expect, it } from 'vitest'
import type { GraphLink, GraphNode } from '@/api/client'
import { MISSING_YEARS_HINT, TIME_AXIS_LABELS, timelineLayout, UNKNOWN_LANE } from './timelineModel'

const link = (source: string, target: string, kind: GraphLink['kind'], label: string | null = null): GraphLink => ({
  source,
  target,
  kind,
  id: null,
  label,
})

const node = (id: string, title: string, year: number | null, addedAt = '2026-09-13T10:00:00Z'): GraphNode => ({
  id,
  title,
  year,
  workspaces: [],
  has_notes: false,
  status: 'ready',
  added_at: addedAt,
})

// 1000 wide: 48 px each side, so the axis runs over 904 px. 400 high: the axis at 368, papers 16 px apart above it.
const BOX = { width: 1000, height: 400 }

/** An arc's path "M x1 y1 Q cx cy x2 y2" as [x1, y1, cx, cy, x2, y2]. */
const points = (path: string) => path.split(' ').filter((token) => token !== 'M' && token !== 'Q').map(Number)

describe('the timeline by year published', () => {
  const nodes = [node('a', 'Beta', 2023), node('b', 'Alpha', 2023), node('c', 'Gamma', 2025), node('d', 'Delta', null)]

  it('gives every year from the first to the last a tick, and undated papers a last lane', () => {
    const layout = timelineLayout(nodes, [], 'published', BOX)
    // Four equal slots of 226 px: 2023, 2024 (empty, still a tick), 2025, Year unknown.
    expect(layout.ticks).toEqual([
      { x: 161, label: '2023' },
      { x: 387, label: '2024' },
      { x: 613, label: '2025' },
      { x: 839, label: 'Year unknown' },
    ])
    expect(layout.hasUnknown).toBe(true)
    expect(UNKNOWN_LANE).toBe('Year unknown')
    expect(MISSING_YEARS_HINT).toBe('Turn on OpenAlex in Settings to fill in missing years.')
  })

  it('stacks papers of one year upwards from the axis, by title', () => {
    const layout = timelineLayout(nodes, [], 'published', BOX)
    expect(layout.axisY).toBe(368)
    expect(layout.dots.map((dot) => [dot.node.id, dot.x, dot.y])).toEqual([
      ['b', 161, 352],
      ['a', 161, 336],
      ['c', 613, 352],
      ['d', 839, 352],
    ])
  })

  it('has no unknown lane when every paper has a year', () => {
    const layout = timelineLayout([node('a', 'A', 2024), node('b', 'B', 2024)], [], 'published', BOX)
    expect(layout.ticks).toEqual([{ x: 500, label: '2024' }])
    expect(layout.hasUnknown).toBe(false)
  })

  it('squeezes a tall stack to fit under the top of the box', () => {
    const many = Array.from({ length: 40 }, (_, n) => node(`p${n}`, `Paper ${String(n).padStart(2, '0')}`, 2024))
    const top = Math.min(...timelineLayout(many, [], 'published', BOX).dots.map((dot) => dot.y))
    expect(top).toBeGreaterThanOrEqual(16)
  })
})

describe('the timeline by date added', () => {
  const nodes = [
    node('a', 'A', 2020, '2026-07-30T12:00:00Z'),
    node('c', 'C', null, '2026-09-13T20:00:00Z'),
    node('b', 'B', null, '2026-09-13T08:00:00Z'),
    node('d', 'D', null, '2026-09-18T01:00:00Z'),
  ]
  const layout = timelineLayout(nodes, [], 'added', BOX)
  const round = (value: number) => Math.round(value * 10) / 10

  it('runs from the first day a paper was added to the last, and places every paper', () => {
    // 30 July to 18 September is 50 days over 904 px; 13 September is day 45.
    expect(layout.dots.map((dot) => [dot.node.id, round(dot.x), dot.y])).toEqual([
      ['a', 48, 352],
      ['b', 861.6, 352],
      ['c', 861.6, 336],
      ['d', 952, 352],
    ])
    expect(layout.hasUnknown).toBe(false)
  })

  it('ticks by month: the first at the start of the axis, then every month start inside it', () => {
    expect(layout.ticks.map((tick) => [round(tick.x), tick.label])).toEqual([
      [48, 'Jul 2026'],
      [84.2, 'Aug 2026'],
      [644.6, 'Sep 2026'],
    ])
    expect(TIME_AXIS_LABELS).toEqual({ published: 'Year published', added: 'Date added' })
  })

  it('centres a library added in one day', () => {
    const one = timelineLayout([node('a', 'A', null)], [], 'added', BOX)
    expect(one.dots.map((dot) => dot.x)).toEqual([500])
    expect(one.ticks).toEqual([{ x: 500, label: 'Sep 2026' }])
  })
})

describe('the timeline’s arcs', () => {
  const nodes = [node('a', 'A', 2020), node('b', 'B', 2021), node('c', 'C', 2024), node('e', 'E', 2020)]
  const links = [link('a', 'b', 'cites'), link('a', 'c', 'manual', 'builds on'), link('a', 'e', 'similar')]
  const layout = timelineLayout(nodes, links, 'published', BOX)
  const at = (id: string) => {
    const dot = layout.dots.find((candidate) => candidate.node.id === id)
    return [dot?.x, dot?.y]
  }

  it('run from one paper’s dot to the other’s, drawn in the direction of the link', () => {
    const [near] = layout.arcs
    const [x1, y1, , , x2, y2] = points(near.path)
    expect([x1, y1]).toEqual(at('a'))
    expect([x2, y2]).toEqual(at('b'))
    expect([near.source, near.target, near.kind]).toEqual(['a', 'b', 'cites'])
  })

  it('rise higher the further apart the papers are', () => {
    const [near, far] = layout.arcs
    expect(points(far.path)[3]).toBeLessThan(points(near.path)[3])
    expect(far.title).toBe('A and C: Your links (builds on)')
  })

  it('bow sideways between two papers of the same year instead of running through the stack', () => {
    const [x1, , cx] = points(layout.arcs[2].path)
    expect(cx).toBeGreaterThan(x1)
  })
})
