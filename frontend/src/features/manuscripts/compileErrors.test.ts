import { expect, test } from 'vitest'
import { errorsFor, friendlyCompileCode } from './compileErrors'

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

test('finds the friendly code from the log', () => {
  expect(friendlyCompileCode({ compile_status: 'failed', compile_log: "this bundle isn't cached", compile_errors: [] })).toBe('needs_download')
  expect(friendlyCompileCode({ compile_status: 'failed', compile_log: 'Running external tool biber', compile_errors: [] })).toBe('biber_unsupported')
  expect(friendlyCompileCode({ compile_status: 'failed', compile_log: 'accessing absolute path /etc', compile_errors: [] })).toBe('outside_file')
  expect(friendlyCompileCode({ compile_status: 'failed', compile_log: '', compile_errors: [] })).toBe('compile_timeout')
  expect(friendlyCompileCode({ compile_status: 'ok', compile_log: '', compile_errors: [] })).toBeNull()
})
