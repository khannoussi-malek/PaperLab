import { expect, test } from 'vitest'
import type { ProvNode } from '@/api/client'
import { keyPaperIds, mapOrigin, mapPositions, NO_YEAR_X, tickX, YEAR_W, yearTicks } from './mapModel'

const n = (id: string, level: number, year: number | null, paths = 1): ProvNode => ({ id, title: id, level, year, decision: null, snowballed: [], paths })

test('key papers are the 10 with the most incoming paths, ties by id, only papers with more than one route', () => {
  const nodes = Array.from({ length: 15 }, (_, i) => n(`P${String(i).padStart(2, '0')}`, 0, 2020, i < 12 ? 2 + (i % 3) : 1))
  const keys = keyPaperIds(nodes)
  expect(keys.size).toBe(10)
  expect(keys.has('P12')).toBe(false) // one route only
  expect(keyPaperIds([n('a', 0, 2020, 1)]).size).toBe(0)
})

test('key papers rank visible papers only', () => {
  const nodes = [n('a', 0, 2020, 9), n('b', 0, 2020, 3)]
  expect([...keyPaperIds(nodes, 10, new Set(['a']))]).toEqual(['b'])
})

test('a tick sits where the papers of that year are drawn', () => {
  const nodes = [n('a', 0, 2003), n('b', 0, 2021), n('c', 0, 2010), n('d', 0, 2015)]
  const pos = mapPositions(nodes)
  for (const t of yearTicks(nodes)) {
    const same = nodes.filter((p) => p.year === t)
    for (const p of same) expect(Math.abs(pos.get(p.id)!.x - tickX(nodes, t))).toBeLessThanOrEqual(YEAR_W * 0.35 + 1e-9)
  }
  expect(tickX(nodes, 2010)).toBe((2010 - mapOrigin(nodes)) * YEAR_W)
})

test('new node objects with the same ids land in the same places', () => {
  const nodes = [n('a', 0, 2010), n('b', 1, 2020)]
  expect(mapPositions(nodes.map((p) => ({ ...p })), 300)).toEqual(mapPositions(nodes, 300))
})

test('y is spread within a level and stable across calls', () => {
  const nodes = Array.from({ length: 30 }, (_, i) => n(`id${i}`, 0, 2020))
  const a = mapPositions(nodes)
  const ys = [...a.values()].map((p) => p.y)
  expect(new Set(ys).size).toBeGreaterThan(25)
  expect(mapPositions(nodes)).toEqual(a)
})

test('year ticks fall on multiples of 5', () => {
  expect(yearTicks([n('a', 0, 2003), n('b', 0, 2021)])).toEqual([2005, 2010, 2015, 2020])
})

test('positions are stable: x by year, y by level, no-year lane at the far left', () => {
  const nodes = [n('a', 0, 2010), n('b', 1, 2020), n('c', 1, 2020), n('d', 2, null)]
  const one = mapPositions(nodes)
  expect(mapPositions([...nodes].reverse())).toEqual(one)
  expect(one.get('b')!.x).toBeGreaterThan(one.get('a')!.x)
  expect(Math.abs(one.get('d')!.x - NO_YEAR_X)).toBeLessThanOrEqual(21)
  expect(one.get('d')!.x).toBeLessThan(one.get('a')!.x)
  expect(one.get('b')!.y).not.toBe(one.get('c')!.y)
  expect(one.get('a')!.y).toBeLessThan(one.get('d')!.y)
})

test('the y spread follows the height asked for, with room at both ends', () => {
  const nodes = [...Array.from({ length: 20 }, (_, i) => n(`a${i}`, 0, 2020)), ...Array.from({ length: 20 }, (_, i) => n(`b${i}`, 1, 2021))]
  const ys = [...mapPositions(nodes, 400).values()].map((p) => p.y)
  expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(250)
  expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(400)
})
