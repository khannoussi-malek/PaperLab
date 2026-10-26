import { expect, test } from 'vitest'
import { ApiError } from '@/api/client'
import { manuscriptErrorMessage, manuscriptFailure } from './errors'

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

test('manuscriptFailure: mapped code gets its copy, unmapped keeps the server message, none gets the generic one', () => {
  expect(manuscriptFailure(new ApiError('file_exists', 409, { detail: 'file_exists' }))).toBe(manuscriptErrorMessage('file_exists'))
  expect(manuscriptFailure(new ApiError('Compile queue is full', 503, { detail: 'Compile queue is full' }))).toBe('Compile queue is full')
  expect(manuscriptFailure(new Error('Network down'))).toBe('Network down')
  expect(manuscriptFailure(new Error(''))).toBe('Something went wrong. Please try again.')
})
