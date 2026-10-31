// @vitest-environment jsdom
import { fireEvent } from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { isUserScroll, usePdfInteraction } from './usePdfInteraction'

let now = 1000
let box: HTMLDivElement
beforeEach(() => {
  now = 1000
  vi.spyOn(performance, 'now').mockImplementation(() => now)
  box = document.createElement('div')
  box.innerHTML = '<p>inside</p>'
  document.body.append(box)
})
afterEach(() => { box.remove(); vi.restoreAllMocks() })

const setup = () => {
  const onInteract = vi.fn()
  renderHook(() => usePdfInteraction({ current: box }, onInteract))
  return onInteract
}

it('isUserScroll: a scroll within 300 ms of input', () => {
  expect(isUserScroll(1000, 1299)).toBe(true)
  expect(isUserScroll(1000, 1301)).toBe(false)
  expect(isUserScroll(null, 1000)).toBe(false)
})

it.each(['wheel', 'touchMove', 'pointerDown'] as const)('%s then scroll counts', (ev) => {
  const on = setup()
  fireEvent[ev](box)
  now += 100
  fireEvent.scroll(box)
  expect(on).toHaveBeenCalledTimes(1)
})

it('a scroll key then scroll counts', () => {
  const on = setup()
  fireEvent.keyDown(box, { key: 'ArrowDown' })
  fireEvent.scroll(box)
  expect(on).toHaveBeenCalledTimes(1)
})

it('a bare scroll (reflow, measuring, zoom re-place) is not an interaction', () => {
  const on = setup()
  fireEvent.scroll(box)
  fireEvent.wheel(box)
  now += 400
  fireEvent.scroll(box)
  expect(on).not.toHaveBeenCalled()
})

const select = (anchorNode: Node | null, isCollapsed = false) => {
  vi.spyOn(window, 'getSelection').mockReturnValue({ isCollapsed, anchorNode } as Selection)
  document.dispatchEvent(new Event('selectionchange'))
}

it('a non-collapsed selection inside counts; collapsed or outside does not', () => {
  const on = setup()
  select(box.firstChild!, true)
  select(document.body)
  expect(on).not.toHaveBeenCalled()
  select(box.querySelector('p')!.firstChild)
  expect(on).toHaveBeenCalledTimes(1)
})
