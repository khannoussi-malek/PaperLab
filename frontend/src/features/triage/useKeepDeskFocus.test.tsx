// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useKeepDeskFocus } from './useKeepDeskFocus'

function Desk({ child = true }: { child?: boolean }) {
  const root = useRef<HTMLElement>(null)
  useKeepDeskFocus(root)
  return <section ref={root} tabIndex={0} data-testid="desk">{child && <button>inside</button>}</section>
}
const root = () => document.querySelector<HTMLElement>('[data-testid="desk"]')!

beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanup(); vi.useRealTimers(); document.body.innerHTML = '' })

// Chromium fires focusout (relatedTarget null) while the element is still connected, then removes it.
it('returns focus to the desk when the focused element is removed after its focusout', () => {
  render(<Desk />)
  const button = root().querySelector('button')!
  button.focus()
  act(() => { button.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null })) })
  expect(button.isConnected).toBe(true)
  act(() => { button.remove() })
  act(() => { vi.runAllTimers() })
  expect(document.activeElement).toBe(root())
})

it('leaves focus alone when it moved to another element', () => {
  render(<Desk />)
  const other = document.body.appendChild(document.createElement('input'))
  const button = root().querySelector('button')!
  button.focus()
  act(() => { button.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: other })) })
  other.focus()
  act(() => { vi.runAllTimers() })
  expect(document.activeElement).toBe(other)
})

it('does not steal focus while a dialog is open', () => {
  render(<Desk />)
  const dialog = document.body.appendChild(document.createElement('div'))
  dialog.setAttribute('role', 'dialog')
  dialog.setAttribute('data-state', 'open')
  const button = root().querySelector('button')!
  button.focus()
  act(() => { button.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null })) })
  button.blur()
  act(() => { vi.runAllTimers() })
  expect(document.activeElement).toBe(document.body)
})

it('cancels the pending check on unmount', () => {
  const { unmount } = render(<Desk />)
  const r = root()
  const button = r.querySelector('button')!
  button.focus()
  act(() => { button.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null })) })
  button.blur()
  unmount()
  const spy = vi.spyOn(r, 'focus')
  act(() => { vi.runAllTimers() })
  expect(spy).not.toHaveBeenCalled()
})

it('leaves focus alone after a press outside the desk on dead space', () => {
  render(<Desk />)
  const button = root().querySelector('button')!
  button.focus()
  act(() => {
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    button.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }))
    button.blur()
  })
  act(() => { vi.runAllTimers() })
  expect(document.activeElement).not.toBe(root())
})
