import { expect, test } from 'vitest'
import type { ProvLink, ProvNode, ProvRoot } from '@/api/client'
import { tidyLayout } from './layout'
import { RING, toRadial } from './radial'

const roots: ProvRoot[] = [{ id: 'root:r1', label: 's', hit_count: 2, on_tree: 2, excluded_hidden: 0 }]
const node = (id: string, level: number): ProvNode => ({ id, title: id, level, decision: null, snowballed: [], paths: 1 })
const nodes = [node('A', 0), node('B', 1), node('C', 1)]
const link = (parent: string, child: string, i: number): ProvLink => ({ parent, child, kind: 'cites', run_id: 'r1', created_at: `2026-01-01T00:00:0${i}Z` })
const links = [link('root:r1', 'A', 0), link('A', 'B', 1), link('A', 'C', 2)]

test('boxes on level n sit at radius (n+1)*90 and roots at the centre', () => {
  const layout = tidyLayout(nodes, links, roots, new Set(), new Set())
  const out = new Map(toRadial(layout).map((b) => [b.box.id, b]))
  expect(RING).toBe(90)
  expect(out.get('A')!.radius).toBe(90)
  expect(out.get('B')!.radius).toBe(180)
  expect(out.get('root:r1')!.radius).toBeLessThan(30)
  const b = out.get('B')!
  expect(b.angle).toBeCloseTo((b.box.y / layout.height) * 2 * Math.PI)
  expect(Math.hypot(b.x, b.y)).toBeCloseTo(180)
})
