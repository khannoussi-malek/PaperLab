import { expect, test } from 'vitest'
import { latexTitle, parseBlueprint, starterBlueprint } from './blueprint'

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

test('the starter has the title, empty lists and the template bands', () => {
  const text = starterBlueprint('My paper', { introduction: [400, 900], method: [500, 1500] })
  expect(JSON.parse(text)).toEqual({ title: 'My paper', contributions: [], notation: [], target_words: { introduction: [400, 900], method: [500, 1500] } })
  expect(text.endsWith('\n')).toBe(true)
  expect(text).toContain('\n  "title"')
})

test('no bands gives an empty target_words', () => {
  expect(JSON.parse(starterBlueprint('T', undefined)).target_words).toEqual({})
})

test.each([
  ['\\title{What Works}', 'What Works'],
  ['\\title[Short]{Long \\\\ Title}', 'Long Title'],
  ['\\title{A\\thanks{Funded by X.} B}', 'A B'],
  ['\\title{Retrieval~at Scale}', 'Retrieval at Scale'],
  ['% \\title{Old}\n\\title{New}', 'New'],
  ['\\title{\\textbf{Bold} words}', 'Bold words'],
  ['\\title{Foo\\\\ \\large Bar}', 'Foo Bar'],
  ['\\title{Line one\\newline line two}', 'Line one line two'],
  ['\\title{Half 50\\% done % a comment\n}', 'Half 50% done'],
  ['\\title{Nested {braces} stay}', 'Nested braces stay'],
  ['\\title{}', null],
  ['\\title{\\thanks{only a note}}', null],
  ['\\section{No title here}', null],
  ['\\title{Unclosed', null],
])('latexTitle(%j) is %j', (tex, want) => {
  expect(latexTitle(tex)).toBe(want)
})
