import { expect, test } from 'vitest'
import { errorsFor, parseCompileErrors } from './compileErrors'

const errors = [
  { file: 'main.tex', line: 4, message: 'Undefined control sequence', kind: 'error' },
  { file: 'sec/a.tex', line: 2, message: 'Missing $', kind: 'error' },
  { file: 'main.tex', line: null, message: 'no line', kind: 'warning' },
  { file: 'main.tex', line: 9, message: 'Citation missing', kind: 'warning' },
]

test('filters by file', () => {
  expect(errorsFor(errors, 'main.tex')).toEqual([
    { line: 4, message: 'Undefined control sequence' },
    { line: 9, message: 'Citation missing' },
  ])
  expect(errorsFor(errors, 'sec/a.tex')).toEqual([{ line: 2, message: 'Missing $' }])
  expect(errorsFor(null, 'main.tex')).toEqual([])
})

test('an engine error with no file is kept, and points at no line', () => {
  const engine = { file: null, line: null, message: 'Could not locate a font', kind: 'engine' }
  expect(parseCompileErrors([engine])).toEqual([engine])
  expect(errorsFor([engine], 'main.tex')).toEqual([])
})
