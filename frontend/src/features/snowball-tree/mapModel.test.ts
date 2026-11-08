import { expect, test } from 'vitest'
import type { ProvNode } from '@/api/client'
import { keyPaperIds, mapPositions, NO_YEAR_X } from './mapModel'

const n = (id: string, level: number, year: number | null, paths = 1): ProvNode => ({ id, title: id, level, year, decision: null, snowballed: [], paths })

test('key papers are the 10 with the most incoming paths, ties broken by id', () => {
  const nodes = Array.from({ length: 15 }, (_, i) => n(`P${String(i).padStart(2, '0')}`, 0, 2020, i < 3 ? 9 : 1))
  const keys = keyPaperIds(nodes)
  expect(keys.size).toBe(10)
  for (const id of ['P00', 'P01', 'P02', 'P03', 'P09']) expect(keys.has(id)).toBe(true)
  expect(keys.has('P14')).toBe(false)
})

test('positions are stable: x by year, y by level, no-year lane at the far left', () => {
  const nodes = [n('a', 0, 2010), n('b', 1, 2020), n('c', 1, 2020), n('d', 2, null)]
  const one = mapPositions(nodes)
  expect(mapPositions([...nodes].reverse())).toEqual(one)
  expect(one.get('b')!.x).toBeGreaterThan(one.get('a')!.x)
  expect(one.get('d')!.x).toBe(NO_YEAR_X)
  expect(NO_YEAR_X).toBeLessThan(one.get('a')!.x)
  expect(one.get('b')!.y).not.toBe(one.get('c')!.y)
  expect(one.get('a')!.y).toBeLessThan(one.get('b')!.y)
})
