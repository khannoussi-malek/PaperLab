import { expect, test } from 'vitest'
import { manuscriptErrorMessage } from './errors'

test('names the path, limit and cause where there is one', () => {
  expect(manuscriptErrorMessage('bad_path', { path: 'a/../b.tex' })).toContain('a/../b.tex')
  expect(manuscriptErrorMessage('reserved_path', { path: 'main.pdf' })).toContain('main.pdf')
  expect(manuscriptErrorMessage('bad_zip', { path: 'x.zip' })).toContain('x.zip')
  expect(manuscriptErrorMessage('file_too_large', { limit: 5 * 1024 * 1024 })).toContain('5 MB')
})

test.each([
  'file_changed', 'file_exists', 'bad_path', 'reserved_path', 'unsupported_file_type', 'file_too_large',
  'manuscript_too_large', 'too_many_files', 'bad_zip', 'no_main_file', 'not_text', 'main_file_not_tex',
  'unknown_template', 'no_pdf',
])('%s has a plain sentence, not the code', (code) => {
  const text = manuscriptErrorMessage(code, {})
  expect(text).not.toContain(code)
  expect(text.endsWith('.')).toBe(true)
})

test('an unknown code falls back to a generic sentence', () => {
  expect(manuscriptErrorMessage('boom')).toBe('Something went wrong. Please try again.')
})
