import { expect, test } from 'vitest'
import type { SnowballStats } from '@/api/client'
import { friendlySnowballError, snowballLine } from './snowballText'

const seed = (found: { cites: number; cited_by: number }, o: object = {}) => ({
  id: 's', kind: 'paper' as const, title: 't', found, new: { cites: 0, cited_by: 0 }, skipped: null, error: null,
  errors: { cites: null, cited_by: null }, done: [], hit_id: null, ...o,
})

test('snowballLine sums found counts and counts skipped seeds', () => {
  const s: SnowballStats = {
    directions: ['cites', 'cited_by'],
    seeds: [seed({ cites: 10, cited_by: 7 }), seed({ cites: 20, cited_by: 5 }, { skipped: 'no id' })],
  }
  expect(snowballLine(s)).toEqual({ counts: '12 citing · 30 cited · 1 skipped', error: null })
})

test('snowballLine returns the first seed error, made friendly', () => {
  const s: SnowballStats = {
    directions: ['cites'],
    seeds: [seed({ cites: 0, cited_by: 0 }, { error: 'HTTP 429 from api.semanticscholar.org' })],
  }
  expect(snowballLine(s).error).toBe('Semantic Scholar refused: add a free key in Settings → Paper sources.')
})

test('friendlySnowballError maps 429 and 401, passes others through', () => {
  const msg = 'Semantic Scholar refused: add a free key in Settings → Paper sources.'
  expect(friendlySnowballError('HTTP 429 from api.semanticscholar.org')).toBe(msg)
  expect(friendlySnowballError('401 Unauthorized')).toBe(msg)
  expect(friendlySnowballError("Client error '429 Too Many Requests' for url 'https://api.x'")).toBe(msg)
  expect(friendlySnowballError('boom')).toBe('boom')
})

test('friendlySnowballError ignores a status number inside a DOI or other text', () => {
  const doi = 'Not found: 10.1234/abc.4291'
  expect(friendlySnowballError(doi)).toBe(doi)
  expect(friendlySnowballError('doi 10.429/401x failed')).toBe('doi 10.429/401x failed')
})
