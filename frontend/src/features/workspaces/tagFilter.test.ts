import { describe, expect, it } from 'vitest'
import type { Paper } from '../../api/client'
import { filterByTags } from './tagFilter'

const p = (id: string) => ({ id }) as Paper
const papers = [p('1'), p('2'), p('3')]
const map = { '1': ['a', 'b'], '2': ['a'], '3': ['c'] }
const known = ['a', 'b', 'c', 'empty']
const ids = (list: Paper[]) => list.map((x) => x.id)

describe('filterByTags', () => {
  it('gives everything for an empty selection', () => {
    expect(ids(filterByTags(papers, map, [], 'any', known))).toEqual(['1', '2', '3'])
  })

  it('any: papers with at least one selected tag', () => {
    expect(ids(filterByTags(papers, map, ['b', 'c'], 'any', known))).toEqual(['1', '3'])
  })

  it('all: papers carrying every selected tag', () => {
    expect(ids(filterByTags(papers, map, ['a', 'b'], 'all', known))).toEqual(['1'])
  })

  it('ignores a selected tag that no longer exists', () => {
    expect(ids(filterByTags(papers, map, ['a', 'gone'], 'all', known))).toEqual(['1', '2'])
    expect(ids(filterByTags(papers, map, ['gone'], 'any', known))).toEqual(['1', '2', '3'])
  })

  it('a known tag with no papers gives an empty list, for any and all', () => {
    expect(ids(filterByTags(papers, map, ['empty'], 'any', known))).toEqual([])
    expect(ids(filterByTags(papers, map, ['a', 'empty'], 'all', known))).toEqual([])
  })
})
