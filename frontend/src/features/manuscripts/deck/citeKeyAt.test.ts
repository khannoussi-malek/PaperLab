import { expect, it } from 'vitest'
import { citeKeyAt } from './citeKeyAt'

const line = 'See \\citep[p.~3]{lewis20, smith19} and \\cite{x}.'
it('finds the key under the cursor in a key list', () => {
  expect(citeKeyAt(line, line.indexOf('lewis20') + 2)).toBe('lewis20')
  expect(citeKeyAt(line, line.indexOf('smith19') + 7)).toBe('smith19')
  expect(citeKeyAt(line, line.indexOf('{x}') + 1)).toBe('x')
})
it('is null outside the braces or in a comment', () => {
  expect(citeKeyAt(line, 1)).toBeNull()
  expect(citeKeyAt('% \\cite{a}', 9)).toBeNull()
  expect(citeKeyAt('\\ref{a}', 6)).toBeNull()
})
