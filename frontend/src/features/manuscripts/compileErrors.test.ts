import { expect, test } from 'vitest'
import { errorsFor } from './compileErrors'

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
