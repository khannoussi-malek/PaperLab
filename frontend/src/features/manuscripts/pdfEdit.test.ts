import { expect, test } from 'vitest'
import { findEditable, replaceSpan } from './pdfEdit'

const lines = ['We study cats. Dogs are \\textbf{loud}! Birds sing.', 'second line', 'third line', 'The ocean is wide.', 'Cited in \\cite{smith2020}.']

test('picks the sentence that holds the word', () => {
  expect(findEditable(lines, 1, 'Dogs')).toEqual({ line: 1, start: 15, end: 38 })
  expect(findEditable(lines, 1, 'Birds')).toEqual({ line: 1, start: 39, end: 50 })
  expect(findEditable(lines, 1, 'cats.')).toEqual({ line: 1, start: 0, end: 14 }) // punctuation around the word is ignored
})

test('finds a word that moved two lines down, and not one that is absent', () => {
  expect(findEditable(lines, 2, 'ocean')).toEqual({ line: 4, start: 0, end: 18 })
  expect(findEditable(['a', 'b', 'c', 'd', 'ocean x.'], 1, 'ocean')).toBeNull() // four lines away is out of range
})

test('a label made by LaTeX is not in the source', () => {
  expect(findEditable(lines, 5, '2020')).toBeNull()
  expect(findEditable(lines, 5, '[1]')).toBeNull()
  expect(findEditable(lines, 1, 'textbf')).toBeNull() // commands are ignored when matching
  expect(findEditable(lines, 1, 'loud')).not.toBeNull()
})

test('whole words only', () => {
  expect(findEditable(lines, 1, 'cat')).toBeNull()
})

test('replaceSpan keeps the rest of the line', () => {
  expect(replaceSpan('a\nWe study cats. Dogs bark.\nz', { line: 2, start: 15, end: 25 }, 'Cats purr.')).toBe('a\nWe study cats. Cats purr.\nz')
  expect(replaceSpan('one', { line: 1, start: 0, end: 3 }, 'x\ny')).toBe('x\ny')
})
