// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useCardClock } from './useCardClock'

let t = 0
const now = () => t
let visibility: 'visible' | 'hidden'
beforeEach(() => {
  t = 0
  visibility = 'visible'
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
  vi.spyOn(document, 'hasFocus').mockReturnValue(true)
})
afterEach(() => vi.restoreAllMocks())

const mount = (pdfShown = true) =>
  renderHook(({ id, shown }) => useCardClock(id, { pdfShown: shown }, now), { initialProps: { id: 'a', shown: pdfShown } })

it('a column that is only visible reports pdf_ms but not pdf_opened', () => {
  const { result } = mount()
  t = 5000
  expect(result.current.read()).toEqual({ card_ms: 5000, pdf_ms: 5000, pdf_opened: false })
})

it('no pdf_ms while the tab is hidden or the window blurred', () => {
  const { result } = mount()
  t = 1000
  act(() => { visibility = 'hidden'; document.dispatchEvent(new Event('visibilitychange')) })
  t = 4000
  act(() => { visibility = 'visible'; document.dispatchEvent(new Event('visibilitychange')) })
  t = 5000
  act(() => { window.dispatchEvent(new Event('blur')) })
  t = 9000
  expect(result.current.read()).toMatchObject({ card_ms: 2000, pdf_ms: 2000 })
  act(() => { window.dispatchEvent(new Event('focus')) })
  t = 10000
  expect(result.current.read().card_ms).toBe(3000)
})

it('interact flips pdf_opened only with the column shown', () => {
  const off = mount(false)
  off.result.current.interact()
  expect(off.result.current.read().pdf_opened).toBe(false)
  const on = mount(true)
  on.result.current.interact()
  expect(on.result.current.read().pdf_opened).toBe(true)
})

it('a new card (or an undone one coming back) starts with a fresh clock', () => {
  const { result, rerender } = mount()
  t = 3000
  result.current.interact()
  rerender({ id: 'b', shown: true })
  t = 3500
  expect(result.current.read()).toEqual({ card_ms: 500, pdf_ms: 500, pdf_opened: false })
  result.current.interact()
  rerender({ id: 'a', shown: true })
  expect(result.current.read().pdf_opened).toBe(false)
})
