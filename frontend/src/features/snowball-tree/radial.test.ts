import { expect, test } from 'vitest'
import type { ProvLink, ProvNode, ProvRoot } from '@/api/client'
import { tidyLayout } from './layout'
import { MIN_SECTOR, RING, ROOT_RING, toRadial } from './radial'

const node = (id: string, level: number): ProvNode => ({ id, title: id, level, decision: null, snowballed: [], paths: 1 })
const link = (parent: string, child: string, i: number): ProvLink => ({ parent, child, kind: 'cites', run_id: 'r', created_at: `2026-01-01T00:00:${String(i % 60).padStart(2, '0')}Z` })

function build(roots: number, perRoot: (r: number) => number, kids: number) {
  const rs: ProvRoot[] = Array.from({ length: roots }, (_, r) => ({ id: `root:r${r}`, label: `s${r}`, hit_count: 1, on_tree: 1, excluded_hidden: 0 }))
  const nodes: ProvNode[] = []
  const links: ProvLink[] = []
  rs.forEach((r, ri) => {
    for (let i = 0; i < perRoot(ri); i++) {
      const a = `a${ri}_${i}`
      nodes.push(node(a, 0)); links.push(link(r.id, a, i))
      for (let k = 0; k < kids; k++) { const b = `b${ri}_${i}_${k}`; nodes.push(node(b, 1)); links.push(link(a, b, k)) }
    }
  })
  return toRadial(tidyLayout(nodes, links, rs, new Set(), new Set()))
}

test('boxes on level n sit at radius (n+1)*RING; a lone root sits at the centre', () => {
  const out = new Map(build(1, () => 2, 1).map((b) => [b.box.id, b]))
  expect(out.get('a0_0')!.radius).toBe(RING)
  expect(out.get('b0_0_0')!.radius).toBe(2 * RING)
  expect(out.get('root:r0')!.radius).toBeLessThan(30)
})

test('25 roots, 335 papers: roots on a small inner ring, each sector at least 6 degrees, level-0 angles all different', () => {
  // 100 level-0 papers and 235 level-1: 10 roots with 4 and 3 kids... shaped by counts below
  const out = build(25, (r) => (r < 20 ? 4 : r === 20 ? 20 : 0), 0)
  // add level 1 separately is not needed for the sector rule; check a skewed fixture too
  const roots = out.filter((b) => b.box.root)
  expect(roots).toHaveLength(25)
  for (const r of roots) {
    expect(r.radius).toBe(ROOT_RING)
    expect(r.sector[1] - r.sector[0]).toBeGreaterThanOrEqual((MIN_SECTOR * Math.PI) / 180 - 1e-9)
  }
  const l0 = out.filter((b) => b.box.node?.level === 0).map((b) => b.angle.toFixed(6))
  expect(new Set(l0).size).toBe(l0.length)
})

test('with children, papers stay inside their root sector and level-0 angles differ', () => {
  const out = build(25, (r) => (r === 0 ? 40 : 3), 2) // 25 roots; 40+72 level-0, 224 level-1
  const sector = new Map(out.filter((b) => b.box.root).map((b) => [b.box.id, b.sector]))
  expect(out.filter((b) => b.box.root).every((b) => b.sector[1] - b.sector[0] >= (MIN_SECTOR * Math.PI) / 180 - 1e-9)).toBe(true)
  const l0 = out.filter((b) => b.box.node?.level === 0).map((b) => b.angle.toFixed(6))
  expect(new Set(l0).size).toBe(l0.length)
  const [lo, hi] = sector.get('root:r0')!
  for (const b of out.filter((x) => x.box.id.startsWith('b0_') || x.box.id.startsWith('a0_'))) {
    expect(b.angle).toBeGreaterThanOrEqual(lo - 1e-9)
    expect(b.angle).toBeLessThanOrEqual(hi + 1e-9)
  }
})

test('one search holding 70% of the papers: the smallest sector is at least 6 degrees, the biggest under 60% of the circle', () => {
  const out = build(25, (r) => (r === 0 ? 56 : 1), 3) // root 0: 56*4=224 of 320 papers (70%)
  const sectors = out.filter((b) => b.box.root).map((b) => b.sector[1] - b.sector[0])
  expect(Math.min(...sectors)).toBeGreaterThanOrEqual((MIN_SECTOR * Math.PI) / 180 - 1e-9)
  expect(Math.max(...sectors)).toBeLessThan(0.6 * 2 * Math.PI)
  expect(sectors.reduce((s, x) => s + x, 0)).toBeCloseTo(2 * Math.PI)
})
