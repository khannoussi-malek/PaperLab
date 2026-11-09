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

test('a top-level unknown node is a one-entry path', () => {
  const d = { ...prov, nodes: [...prov.nodes, { id: 'run:x:unknown', title: '?', level: 0, snowballed: [], paths: 1 }] } as typeof prov
  expect(primaryPath(d, 'run:x:unknown')).toEqual([e('run:x:unknown', 'search')])
})

test('a hand-added paper starts at root:hand', () => {
  const d = {
    ...prov,
    nodes: [...prov.nodes, { id: 'paper:x', title: 'X', level: 0, snowballed: [], paths: 1 }],
    links: [...prov.links, { parent: 'root:hand', child: 'paper:x', kind: 'hand', run_id: null, created_at: null }],
  } as typeof prov
  expect(primaryPath(d, 'paper:x')).toEqual([e('root:hand', 'hand'), e('paper:x', 'search')])
})

test('parseNav must start at a search, not a paper', () => {
  expect(parseNav('A,B', prov)).toEqual({ path: [], cut: true })
})

test('parseNav keeps the primary link kind when two links join the same pair', () => {
  // The later cited_by link comes first in the array, so a plain find() would pick it; the primary one is the earlier cites.
  const d = {
    ...prov,
    links: [{ parent: 'A', child: 'B', kind: 'cited_by', run_id: 'r1', created_at: '2026-02-01T00:00:00Z' }, ...prov.links],
  } as typeof prov
  const path = primaryPath(d, 'B')
  expect(path[path.length - 1].via).toBe('cites')
  expect(parseNav(toParam(path), d).path).toEqual(path)
})

test('a hand paper with no link round-trips through the URL', () => {
  const d = { ...prov, nodes: [...prov.nodes, { id: 'paper:y', title: 'Y', level: 0, snowballed: [], paths: 1 }] } as typeof prov
  const path = primaryPath(d, 'paper:y')
  expect(path).toEqual([e('root:hand', 'hand'), e('paper:y', 'search')])
  expect(parseNav(toParam(path), d)).toEqual({ path, cut: false })
})

test('root:hand and an unknown node are accepted as first entries', () => {
  const d = {
    ...prov,
    nodes: [...prov.nodes, { id: 'run:x:unknown', title: '?', level: 0, snowballed: [], paths: 1 }],
    links: [...prov.links, { parent: 'root:hand', child: 'paper:x', kind: 'hand', run_id: null, created_at: null }],
  } as typeof prov
  expect(parseNav('root:hand', d)).toEqual({ path: [e('root:hand', 'hand')], cut: false })
  expect(parseNav('run:x:unknown', d)).toEqual({ path: [e('run:x:unknown', 'search')], cut: false })
})
