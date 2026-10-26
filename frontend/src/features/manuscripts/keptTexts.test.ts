// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { keptTexts, useKeptCount, useKeptTexts } from './keptTexts'

const kept = (text: string, seq = 1) => ({ text, reason: 'error' as const, base: 'T1', seq })

beforeEach(() => keptTexts.clear())

test('keeps text per manuscript and path, and tells subscribers', () => {
  const listener = vi.fn()
  const off = keptTexts.subscribe(listener)
  keptTexts.set('m1', 'a.tex', kept('one'))
  keptTexts.set('m1', 'b.tex', kept('two'))
  keptTexts.set('m2', 'a.tex', kept('other'))
  expect(keptTexts.get('m1', 'a.tex')?.text).toBe('one')
  expect(keptTexts.forManuscript('m1')).toEqual({ 'a.tex': kept('one'), 'b.tex': kept('two') })
  expect(keptTexts.count()).toBe(3)
  keptTexts.remove('m1', 'a.tex')
  expect(keptTexts.get('m1', 'a.tex')).toBeUndefined()
  expect(listener).toHaveBeenCalledTimes(4)
  off()
  keptTexts.remove('m1', 'b.tex')
  expect(listener).toHaveBeenCalledTimes(4)
})

test('hooks follow the store', () => {
  const texts = renderHook(() => useKeptTexts('m1'))
  const count = renderHook(() => useKeptCount())
  expect(count.result.current).toBe(0)
  act(() => keptTexts.set('m1', 'a.tex', kept('x')))
  expect(texts.result.current['a.tex'].text).toBe('x')
  expect(count.result.current).toBe(1)
  act(() => keptTexts.remove('m1', 'a.tex'))
  expect(count.result.current).toBe(0)
})

test('an older pane never overwrites a newer pane\'s entry', () => {
  keptTexts.set('m1', 'a.tex', kept('newer', 2))
  keptTexts.set('m1', 'a.tex', kept('older', 1))
  expect(keptTexts.get('m1', 'a.tex')?.text).toBe('newer')
  keptTexts.set('m1', 'a.tex', kept('same pane again', 2))
  expect(keptTexts.get('m1', 'a.tex')?.text).toBe('same pane again')
  keptTexts.set('m1', 'a.tex', kept('newest', 3))
  expect(keptTexts.get('m1', 'a.tex')?.text).toBe('newest')
})

test('hands out rising sequence numbers', () => {
  expect(keptTexts.nextSeq()).toBeLessThan(keptTexts.nextSeq())
})

test('counts saves still in flight as well as kept entries', () => {
  const count = renderHook(() => useKeptCount())
  act(() => keptTexts.flushStarted())
  expect(count.result.current).toBe(1)
  act(() => keptTexts.set('m1', 'a.tex', kept('x')))
  expect(count.result.current).toBe(2)
  act(() => keptTexts.flushSettled())
  expect(count.result.current).toBe(1)
})
