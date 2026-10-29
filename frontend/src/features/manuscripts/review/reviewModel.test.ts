import { describe, expect, test } from 'vitest'
import type { CheckItem } from '@/api/client'
import { citeThisEdit, itemTone, marksFor, VERDICT_LABEL } from './reviewModel'

const item = (o: Partial<CheckItem>): CheckItem => ({ id: 'i', kind: 'cited', sentence_hash: 'h1', verdict: 'supported', ...o }) as CheckItem
const span = (hash: string, start: number, end: number) => ({ hash, start, end, keys: [] })

test('labels and tones', () => {
  expect(VERDICT_LABEL).toMatchObject({ supported: 'Supports', partially_supported: 'Partly supports', not_supported: "Doesn't support", not_addressed: "Doesn't address", cannot_verify: "Can't tell", claim: 'Needs a citation', not_claim: 'Not a claim' })
  const tones = Object.fromEntries(Object.keys(VERDICT_LABEL).map((v) => [v, itemTone({ verdict: v })]))
  expect(tones).toEqual({ supported: 'good', partially_supported: 'warn', not_supported: 'bad', not_addressed: 'muted', cannot_verify: 'muted', claim: 'warn', not_claim: 'muted' })
  expect(itemTone({ verdict: null })).toBe('muted')
})

describe('marksFor', () => {
  test('joins by hash, groups items on one sentence, reports stale', () => {
    const a = item({ id: 'a' }), b = item({ id: 'b' }), c = item({ id: 'c', sentence_hash: 'gone' })
    const { marks, stale } = marksFor([a, b, c], [span('h1', 5, 20)])
    expect(marks).toEqual([{ from: 5, to: 20, items: [a, b] }])
    expect(stale).toEqual([c])
  })
  test('skips dismissed uncited and not_claim', () => {
    const nc = item({ id: 'n', kind: 'uncited', verdict: 'not_claim', sentence_hash: 'h2' })
    const dis = item({ id: 'd', kind: 'uncited', verdict: 'claim', sentence_hash: 'h3' })
    const live = item({ id: 'l', kind: 'uncited', verdict: 'claim', sentence_hash: 'h4' })
    const { marks, stale } = marksFor([nc, dis, live], [span('h2', 0, 1), span('h3', 2, 3), span('h4', 4, 5)], ['h3'])
    expect(marks.map((m) => m.items[0].id)).toEqual(['l'])
    expect(stale).toEqual([])
  })
})

describe('citeThisEdit', () => {
  const run = (doc: string, key = 'k1') => {
    const e = citeThisEdit(doc, { start: 0, end: doc.length }, key)
    expect(e.insert.trim()).toBe(`\\citep{${key}}`)
    return doc.slice(0, e.from) + e.insert + doc.slice(e.from)
  }
  test('plain, question, closers, tilde', () => {
    expect(run('Models help.')).toBe('Models help \\citep{k1}.')
    expect(run('Do models help?')).toBe('Do models help \\citep{k1}?')
    expect(run('(Models help.)')).toBe('(Models help \\citep{k1}.)')
    expect(run('Models help~.')).toBe('Models help~\\citep{k1}.')
  })
  test('unsafe key throws', () => {
    expect(() => citeThisEdit('A b.', { start: 0, end: 4 }, 'a}b')).toThrow()
    expect(() => citeThisEdit('A b.', { start: 0, end: 4 }, '')).toThrow()
  })
})
