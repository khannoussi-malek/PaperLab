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

test('a child hangs under a parent one level up, not just the earliest link', () => {
  // Y (level 0) links to B first, A (level 0) later; B is level 1 via both, so make Y level 1 to be deeper.
  const ns = [node('A', 0), node('Y', 1), node('B', 1)]
  const ls = [link('root:r1', 'A'), link('A', 'Y', '2026-01-02T00:00:00Z'), link('Y', 'B', '2026-01-03T00:00:00Z'), link('A', 'B', '2026-01-04T00:00:00Z')]
  const out = tidyLayout(ns, ls, roots, new Set(), new Set())
  expect(out.edges.find((e) => e.to === 'B')!.from).toBe('A')
  expect(box(out, 'B').x).toBe(2 * COL)
  expect(box(out, 'B').extraPaths).toBe(1)
})

test('a deeper node cannot take a child at its own level', () => {
  const ns = [node('A', 0), node('D', 2), node('B', 1)]
  const ls = [link('D', 'B', '2026-01-01T00:00:00Z'), link('root:r1', 'A'), link('A', 'B', '2026-02-01T00:00:00Z')]
  expect(primaryParent(ls, roots, ns).get('B')!.parent).toBe('A')
})

test('a two-node loop keeps its subtree', () => {
  const ns = [node('A', 0), node('B', 1), node('C', 2)]
  const ls = [link('root:r1', 'A'), link('A', 'B'), link('B', 'A', '2026-02-01T00:00:00Z'), link('B', 'C')]
  const out = tidyLayout(ns, ls, roots, new Set(), new Set())
  expect(out.boxes.map((b) => b.id).sort()).toEqual(['A', 'B', 'C', 'root:r1'])
})

test('a "parent not recorded" node is placed as a root in column 1, its children in column 2', () => {
  const u = 'run:r9:unknown'
  const ns = [node(u, 0), node('L', 1)]
  const out = tidyLayout(ns, [link(u, 'L')], [], new Set(), new Set())
  expect(box(out, u).x).toBe(COL)
  expect(box(out, 'L').x).toBe(2 * COL)
  expect(out.edges).toHaveLength(1)
})

test('a folded node with a matching descendant stays, faded, with the match count', () => {
  const out = tidyLayout(nodes, links, roots, new Set(['A']), new Set(['A', 'B']))
  expect(box(out, 'A').faded).toBe(true)
  expect(box(out, 'A').foldedMatches).toBe(2)
  expect(out.boxes.find((b) => b.id === 'C')).toBeUndefined()
})

test('a root with a matching descendant is not faded', () => {
  const out = tidyLayout(nodes, links, roots, new Set(), new Set(['B', 'D']))
  expect(box(out, 'root:r1').faded).toBe(false)
})
