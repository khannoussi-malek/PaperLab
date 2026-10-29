// @vitest-environment jsdom
import { history, undo } from '@codemirror/commands'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { expect, test } from 'vitest'
import type { CheckItem } from '@/api/client'
import { reviewExtension, reviewHandle } from './reviewMarks'

// jsdom has no layout; CodeMirror's scroll-into-view asks for rects.
Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList

const item = (o: Partial<CheckItem> = {}): CheckItem => ({ id: 'i', kind: 'cited', sentence_hash: 'h1', verdict: 'supported', reason: 'It says so.', ...o }) as CheckItem
const make = (doc: string) => new EditorView({ state: EditorState.create({ doc, extensions: [history(), reviewExtension()] }), parent: document.body })
const hashes = (v: EditorView) => {
  const h = reviewHandle(v, async () => [])
  return { a: h.spanOf('a'), b: h.spanOf('b') }
}

test('marks follow typing before and inside a sentence, and setMarks replaces them', () => {
  const v = make('One. Two three.')
  const h = reviewHandle(v, async () => [])
  h.setMarks([{ from: 5, to: 15, items: [item({ sentence_hash: 'a' })] }])
  expect(h.spanOf('a')).toEqual({ start: 5, end: 15 })
  v.dispatch({ changes: { from: 0, insert: 'XX' } })
  expect(h.spanOf('a')).toEqual({ start: 7, end: 17 })
  v.dispatch({ changes: { from: 10, insert: 'yy' } })
  expect(h.spanOf('a')).toEqual({ start: 7, end: 19 })
  h.setMarks([{ from: 0, to: 3, items: [item({ sentence_hash: 'b' })] }])
  expect(hashes(v)).toEqual({ a: null, b: { start: 0, end: 3 } })
})

test('a mark shows the AI badge and the verdict as text', () => {
  const v = make('Models help.')
  reviewHandle(v, async () => []).setMarks([{ from: 0, to: 12, items: [item()] }])
  expect(v.dom.querySelector('.cm-review-badge')).toHaveTextContent('AI')
  expect(v.dom.querySelector('.cm-review-badge')).toHaveTextContent('Supports')
  expect(v.dom.querySelector('.cm-review-good')).toBeTruthy()
})

test('applyCite inserts exactly the citation before the final period, in one undoable step', async () => {
  const v = make('Models help.')
  const h = reviewHandle(v, async () => [{ hash: 'a', start: 0, end: 12, keys: [] }])
  expect(await h.applyCite('a', 'lewis2020')).toBe('ok')
  expect(v.state.doc.toString()).toBe('Models help \\citep{lewis2020}.')
  undo(v)
  expect(v.state.doc.toString()).toBe('Models help.')
})

test('applyCite refuses when the sentence changed', async () => {
  const v = make('Models help a lot.')
  const h = reviewHandle(v, async () => [{ hash: 'zzz', start: 0, end: 18, keys: [] }])
  expect(await h.applyCite('a', 'k')).toBe('changed')
  expect(v.state.doc.toString()).toBe('Models help a lot.')
})
