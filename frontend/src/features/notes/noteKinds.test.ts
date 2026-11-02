import { expect, test } from 'vitest'
import { KIND_HINT, KIND_LABEL, TEMPLATE, isExitTest, matchesKind, swapTemplate } from './noteKinds'

test('labels and hints', () => {
  expect(KIND_LABEL.five_cs).toBe('Five Cs')
  expect(KIND_LABEL.future_work).toBe('Future work')
  expect(KIND_HINT.five_cs).toBe('Answer each C in a line or two, from your first pass.')
  expect(KIND_HINT.assumption).toBe('An assumption the paper makes here, and whether it holds.')
  expect(KIND_HINT.figure).toBe(TEMPLATE.figure)
})

test('the five Cs template is the headings only', () => {
  expect(TEMPLATE.five_cs).toBe('Category:\nContext:\nCorrectness:\nContributions:\nClarity:')
  expect(TEMPLATE.figure).toBe(
    'Are the axes labelled?\nIs there an error bar or another measure of spread?\nDo the conclusions follow from it?',
  )
  expect(isExitTest('summary')).toBe(true)
  expect(isExitTest('figure')).toBe(false)
  expect(isExitTest(null)).toBe(false)
})

test('matchesKind covers all, one kind and plain notes', () => {
  expect(matchesKind({ kind: null }, 'all')).toBe(true)
  expect(matchesKind({ kind: 'summary' }, 'all')).toBe(true)
  expect(matchesKind({ kind: 'summary' }, 'summary')).toBe(true)
  expect(matchesKind({ kind: 'figure' }, 'summary')).toBe(false)
  expect(matchesKind({ kind: null }, 'plain')).toBe(true)
  expect(matchesKind({ kind: 'summary' }, 'plain')).toBe(false)
})

test('swapTemplate', () => {
  expect(swapTemplate(TEMPLATE.five_cs!, 'five_cs', 'figure')).toBe(TEMPLATE.figure)
  expect(swapTemplate(TEMPLATE.five_cs!, 'five_cs', null)).toBe('')
  expect(swapTemplate('my own words', 'five_cs', 'figure')).toBe('my own words')
  expect(swapTemplate('', null, 'five_cs')).toBe(TEMPLATE.five_cs)
})
