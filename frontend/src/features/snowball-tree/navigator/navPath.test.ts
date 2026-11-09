import { expect, test } from 'vitest'
import { collapse, parseNav, primaryPath, toParam, type NavEntry } from './navPath'
import { prov } from './fixture'

const e = (id: string, via: NavEntry['via'] = 'cites'): NavEntry => ({ id, via })

test('the primary path is the tree parent chain from the search root', () => {
  expect(primaryPath(prov, 'C')).toEqual([e('root:r1', 'search'), e('A', 'search'), e('B'), e('C', 'cited_by')])
})

test('a paper that is not in the data has no path', () => {
  expect(primaryPath(prov, 'nope')).toEqual([])
})

test('parseNav round-trips a good path', () => {
  const path = primaryPath(prov, 'D')
  expect(parseNav(toParam(path), prov)).toEqual({ path, cut: false })
})

test('parseNav cuts at an id that is not in the data', () => {
  const r = parseNav('root:r1,A,B,gone,C', prov)
  expect(r.path.map((x) => x.id)).toEqual(['root:r1', 'A', 'B'])
  expect(r.cut).toBe(true)
})

test('parseNav cuts at an id that is not a child of the previous entry', () => {
  const r = parseNav('root:r1,A,D', prov)
  expect(r.path.map((x) => x.id)).toEqual(['root:r1', 'A'])
  expect(r.cut).toBe(true)
})

test('an empty param is an empty, uncut path', () => {
  expect(parseNav('', prov)).toEqual({ path: [], cut: false })
})

const ids = (n: number) => Array.from({ length: n }, (_, i) => e(`p${i}`))
test('collapse leaves up to 4 entries alone', () => {
  expect(collapse(ids(4))).toEqual(ids(4))
})
test('collapse at 5 and 9 keeps the first, a more marker and the last 2', () => {
  expect(collapse(ids(5))).toEqual([e('p0'), 'more', e('p3'), e('p4')])
  expect(collapse(ids(9))).toEqual([e('p0'), 'more', e('p7'), e('p8')])
})
