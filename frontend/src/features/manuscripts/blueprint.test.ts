import { expect, test } from 'vitest'
import { parseBlueprint } from './blueprint'

test('reads the fields it knows and ignores the rest', () => {
  const b = parseBlueprint('{"title":"T","contributions":["a"],"notation":[{"symbol":"\\\\alpha","meaning":"w"}],"target_words":{"method":[100,200]},"extra":1}')
  expect(b).toEqual({ title: 'T', contributions: ['a'], notation: [{ symbol: '\\alpha', meaning: 'w' }], targets: [{ id: 'method', min: 100, max: 200 }] })
})

test('an empty object is a plan with nothing in it; junk is null', () => {
  expect(parseBlueprint('{}')).toEqual({ title: '', contributions: [], notation: [], targets: [] })
  expect(parseBlueprint('nope')).toBeNull()
  expect(parseBlueprint('[]')).toBeNull()
})

test('malformed entries are dropped, not thrown on', () => {
  const b = parseBlueprint('{"contributions":["a",3],"target_words":{"m":[1],"n":[2,3]}}')
  expect(b?.contributions).toEqual(['a'])
  expect(b?.targets).toEqual([{ id: 'n', min: 2, max: 3 }])
})
