// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { keptTexts, useKeptCount, useKeptTexts } from './keptTexts'

const kept = (text: string) => ({ text, reason: 'error' as const, base: 'T1' })

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
