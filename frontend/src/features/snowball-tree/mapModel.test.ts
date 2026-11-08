import { expect, test } from 'vitest'
import type { ProvNode } from '@/api/client'
import { keyPaperIds, mapPositions, NO_YEAR_X, yearTicks } from './mapModel'

const n = (id: string, level: number, year: number | null, paths = 1): ProvNode => ({ id, title: id, level, year, decision: null, snowballed: [], paths })

test('key papers are the 10 with the most incoming paths, ties broken by id', () => {
  const nodes = Array.from({ length: 15 }, (_, i) => n(`P${String(i).padStart(2, '0')}`, 0, 2020, i < 3 ? 9 : 1))
  const keys = keyPaperIds(nodes)
  expect(keys.size).toBe(10)
  for (const id of ['P00', 'P01', 'P02', 'P03', 'P09']) expect(keys.has(id)).toBe(true)
  expect(keys.has('P14')).toBe(false)
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
