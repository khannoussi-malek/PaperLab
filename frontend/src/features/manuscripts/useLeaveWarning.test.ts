// @vitest-environment jsdom
import { renderHook } from '@testing-library/react'
import { expect, test } from 'vitest'
import { useLeaveWarning } from './useLeaveWarning'

const leave = () => {
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  return event.defaultPrevented
}

test('asks the browser to confirm leaving only while there is something unsaved', () => {
  const { rerender, unmount } = renderHook(({ on }) => useLeaveWarning(on), { initialProps: { on: false } })
  expect(leave()).toBe(false)
  rerender({ on: true })
  expect(leave()).toBe(true)
  rerender({ on: false })
  expect(leave()).toBe(false)
  rerender({ on: true })
  unmount()
  expect(leave()).toBe(false)
})
