// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { keptTexts, useKeptCount, useKeptTexts } from './keptTexts'

const kept = (path: string, text: string, seq: number) => ({ path, text, reason: 'error' as const, base: 'T1', seq })
const texts = (manuscriptId = 'm1') => keptTexts.forManuscript(manuscriptId).map((k) => k.text)

beforeEach(() => keptTexts.clear())

test('keeps text per manuscript, and tells subscribers', () => {
  const listener = vi.fn()
  const off = keptTexts.subscribe(listener)
  const a = keptTexts.put('m1', kept('a.tex', 'one', 1))
  keptTexts.put('m1', kept('b.tex', 'two', 2))
  keptTexts.put('m2', kept('a.tex', 'other', 3))
  expect(keptTexts.forManuscript('m1')).toEqual([{ id: a, ...kept('a.tex', 'one', 1) }, expect.objectContaining({ text: 'two' })])
  expect(keptTexts.count()).toBe(3)
  keptTexts.remove(a)
  expect(texts()).toEqual(['two'])
  expect(listener).toHaveBeenCalledTimes(4)
  off()
  keptTexts.clear()
  expect(listener).toHaveBeenCalledTimes(4)
})

test('hooks follow the store', () => {
  const list = renderHook(() => useKeptTexts('m1'))
  const count = renderHook(() => useKeptCount())
  expect(count.result.current).toBe(0)
  let id = ''
  act(() => { id = keptTexts.put('m1', kept('a.tex', 'x', 1)) })
  expect(list.result.current[0].text).toBe('x')
  expect(count.result.current).toBe(1)
  act(() => keptTexts.remove(id))
  expect(count.result.current).toBe(0)
})

test('a closing pane adds its own entry and never replaces or loses to another pane\'s', () => {
  keptTexts.put('m1', kept('a.tex', 'first pane', 1))
  keptTexts.put('m1', kept('a.tex', 'second pane', 2))
  keptTexts.put('m1', kept('a.tex', 'late first-era pane', 0)) // an older pane failing last still counts
  expect(texts()).toEqual(['first pane', 'second pane', 'late first-era pane'])
})

test('a pane replaces only the entries it adopted and its own earlier write', () => {
  const adopted = keptTexts.put('m1', kept('a.tex', 'kept', 1))
  keptTexts.put('m1', kept('a.tex', 'someone else', 2))
  keptTexts.put('m1', kept('a.tex', 'kept, edited', 3), [adopted])
  expect(texts()).toEqual(['someone else', 'kept, edited'])
  keptTexts.put('m1', kept('a.tex', 'kept, edited again', 3))
  expect(texts()).toEqual(['someone else', 'kept, edited again'])
})

test('remove drops exactly the entry it names', () => {
  const one = keptTexts.put('m1', kept('a.tex', 'one', 1))
  keptTexts.put('m1', kept('a.tex', 'two', 2))
  keptTexts.remove(one)
  expect(texts()).toEqual(['two'])
})

test('hands out rising sequence numbers', () => {
  expect(keptTexts.nextSeq()).toBeLessThan(keptTexts.nextSeq())
})

test('counts saves still in flight as well as kept entries', () => {
  const count = renderHook(() => useKeptCount())
  act(() => keptTexts.flushStarted())
  expect(count.result.current).toBe(1)
  act(() => void keptTexts.put('m1', kept('a.tex', 'x', 1)))
  expect(count.result.current).toBe(2)
  act(() => keptTexts.flushSettled())
  expect(count.result.current).toBe(1)
})
