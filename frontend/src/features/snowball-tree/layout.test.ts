import { expect, test } from 'vitest'
import type { ProvLink, ProvNode, ProvRoot } from '@/api/client'
import { COL, primaryParent, tidyLayout } from './layout'

const node = (id: string, level: number): ProvNode => ({ id, title: id, level, snowballed: [], paths: 1 })
const link = (parent: string, child: string, at = '2026-01-01T00:00:00Z', kind = 'cites'): ProvLink =>
  ({ parent, child, kind, run_id: 'r1', created_at: at })
const roots: ProvRoot[] = [{ id: 'root:r1', label: 'q', hit_count: 5, on_tree: 3 }]

// root -> A -> B, C ; B -> D
const nodes = [node('A', 0), node('B', 1), node('C', 1), node('D', 2)]
const links = [link('root:r1', 'A'), link('A', 'B'), link('A', 'C'), link('B', 'D')]
const box = (out: ReturnType<typeof tidyLayout>, id: string) => out.boxes.find((b) => b.id === id)!

test('a parent sits between its first and last child in y', () => {
  const out = tidyLayout(nodes, links, roots, new Set(), new Set())
  const [b, c, a] = [box(out, 'B'), box(out, 'C'), box(out, 'A')]
  expect(a.y).toBeGreaterThanOrEqual(Math.min(b.y, c.y))
  expect(a.y).toBeLessThanOrEqual(Math.max(b.y, c.y))
  expect(b.y).not.toBe(c.y)
})

test('columns follow the level, search roots in column 0', () => {
  const out = tidyLayout(nodes, links, roots, new Set(), new Set())
  expect(box(out, 'root:r1').x).toBe(0)
  expect(box(out, 'A').x).toBe(COL)
  expect(box(out, 'D').x).toBe(3 * COL)
})

test("a cycle's second link becomes extraPaths and not a box", () => {
  const cyc = [...links, link('B', 'A', '2026-02-01T00:00:00Z')]
  const out = tidyLayout(nodes, cyc, roots, new Set(), new Set())
  expect(out.boxes.filter((b) => b.id === 'A')).toHaveLength(1)
  expect(box(out, 'A').extraPaths).toBe(1)
  expect(out.edges.filter((e) => e.to === 'A')).toHaveLength(1)
})

test('folding A removes B and C', () => {
  const out = tidyLayout(nodes, links, roots, new Set(['A']), new Set())
  expect(out.boxes.map((b) => b.id).sort()).toEqual(['A', 'root:r1'])
})

test('hiding everything except C keeps A and B as faded', () => {
  const out = tidyLayout(nodes, links, roots, new Set(), new Set(['B', 'D']))
  expect(out.boxes.find((b) => b.id === 'B')).toBeUndefined()
  const hiddenEverythingButC = tidyLayout(nodes, links, roots, new Set(), new Set(['A', 'B', 'D']))
  expect(box(hiddenEverythingButC, 'A').faded).toBe(true)
  expect(box(hiddenEverythingButC, 'C').faded).toBe(false)
  expect(hiddenEverythingButC.boxes.find((b) => b.id === 'B')).toBeUndefined()
})

test('primaryParent: earliest link wins, ties go to the first-listed root', () => {
  const two: ProvRoot[] = [...roots, { id: 'root:r2', label: 'q2', hit_count: 1, on_tree: 1 }]
  const tie = [link('root:r2', 'X', '2026-01-01T00:00:00Z'), link('root:r1', 'X', '2026-01-01T00:00:00Z')]
  expect(primaryParent(tie, two).get('X')!.parent).toBe('root:r1')
  const early = [link('root:r1', 'X', '2026-03-01T00:00:00Z'), link('root:r2', 'X', '2026-02-01T00:00:00Z')]
  expect(primaryParent(early, two).get('X')!.parent).toBe('root:r2')
})

test('cited_by edges are dashed', () => {
  const out = tidyLayout([node('A', 0)], [link('root:r1', 'A', undefined, 'cited_by')], roots, new Set(), new Set())
  expect(out.edges[0].dashed).toBe(true)
})
