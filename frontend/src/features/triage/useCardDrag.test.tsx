// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useCardDrag } from './useCardDrag'

afterEach(cleanup)

function Probe(props: { onCommit: (p: string) => void; onCancel: () => void; onProgress?: (dx: number, dy: number, p: string | null) => void; enabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useCardDrag(ref, { enabled: props.enabled ?? true, onCommit: props.onCommit, onCancel: props.onCancel, onProgress: props.onProgress ?? (() => {}) })
  return (
    <div ref={ref} data-testid="card">
      <p data-testid="text">text</p>
      <button>go</button>
      <div aria-label="Abstract" data-testid="abstract">long</div>
    </div>
  )
}

function drag(el: Element, dx: number, dy: number) {
  fireEvent.pointerDown(el, { clientX: 100, clientY: 100, pointerId: 1, button: 0 })
  fireEvent.pointerMove(el, { clientX: 100 + dx, clientY: 100 + dy, pointerId: 1 })
  fireEvent.pointerUp(el, { clientX: 100 + dx, clientY: 100 + dy, pointerId: 1 })
}

it.each([
  [100, 0, 'read_closely'], [-100, 0, 'not_relevant'], [0, -100, 'later'], [0, 100, 'skim'],
])('a drag of (%i,%i) past 80 px commits %s', (dx, dy, pile) => {
  const onCommit = vi.fn(), onCancel = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={onCancel} />)
  drag(screen.getByTestId('text'), dx, dy)
  expect(onCommit).toHaveBeenCalledWith(pile)
  expect(onCancel).not.toHaveBeenCalled()
})

it('a 60 px drag snaps back and cancels', () => {
  const onCommit = vi.fn(), onCancel = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={onCancel} />)
  drag(screen.getByTestId('text'), 60, 0)
  expect(onCommit).not.toHaveBeenCalled()
  expect(onCancel).toHaveBeenCalledTimes(1)
  expect(screen.getByTestId('card').style.transform).toBe('')
})

it('reports progress while moving', () => {
  const onProgress = vi.fn()
  render(<Probe onCommit={vi.fn()} onCancel={vi.fn()} onProgress={onProgress} />)
  fireEvent.pointerDown(screen.getByTestId('text'), { clientX: 0, clientY: 0, pointerId: 1, button: 0 })
  fireEvent.pointerMove(screen.getByTestId('text'), { clientX: 90, clientY: 0, pointerId: 1 })
  expect(onProgress).toHaveBeenLastCalledWith(90, 0, 'read_closely')
})

it('never starts on a button or the abstract scroller', () => {
  const onCommit = vi.fn(), onCancel = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={onCancel} />)
  drag(screen.getByRole('button'), 150, 0)
  drag(screen.getByTestId('abstract'), 150, 0)
  expect(onCommit).not.toHaveBeenCalled()
  expect(onCancel).not.toHaveBeenCalled()
})

it('Escape during a drag cancels it', () => {
  const onCommit = vi.fn(), onCancel = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={onCancel} />)
  const el = screen.getByTestId('text')
  fireEvent.pointerDown(el, { clientX: 100, clientY: 100, pointerId: 1, button: 0 })
  fireEvent.pointerMove(el, { clientX: 220, clientY: 100, pointerId: 1 })
  fireEvent.keyDown(window, { key: 'Escape' })
  fireEvent.pointerUp(el, { clientX: 220, clientY: 100, pointerId: 1 })
  expect(onCancel).toHaveBeenCalledTimes(1)
  expect(onCommit).not.toHaveBeenCalled()
})

it('does nothing when disabled', () => {
  const onCommit = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={vi.fn()} enabled={false} />)
  drag(screen.getByTestId('text'), 150, 0)
  expect(onCommit).not.toHaveBeenCalled()
})

it('a plain click does not cancel', () => {
  const onCancel = vi.fn()
  render(<Probe onCommit={vi.fn()} onCancel={onCancel} />)
  const el = screen.getByTestId('text')
  fireEvent.pointerDown(el, { clientX: 5, clientY: 5, pointerId: 1, button: 0 })
  fireEvent.pointerUp(el, { clientX: 5, clientY: 5, pointerId: 1 })
  expect(onCancel).not.toHaveBeenCalled()
})

it('ignores a second pointer', () => {
  const onCommit = vi.fn()
  render(<Probe onCommit={onCommit} onCancel={vi.fn()} />)
  const el = screen.getByTestId('text')
  fireEvent.pointerDown(el, { clientX: 0, clientY: 0, pointerId: 1, button: 0 })
  fireEvent.pointerUp(el, { clientX: 200, clientY: 0, pointerId: 2 })
  expect(onCommit).not.toHaveBeenCalled()
})

it('unmounting mid-drag restores the body text selection', () => {
  document.body.style.userSelect = 'text'
  const { unmount } = render(<Probe onCommit={vi.fn()} onCancel={vi.fn()} />)
  fireEvent.pointerDown(screen.getByTestId('text'), { clientX: 0, clientY: 0, pointerId: 1, button: 0 })
  expect(document.body.style.userSelect).toBe('none')
  unmount()
  expect(document.body.style.userSelect).toBe('text')
  document.body.style.userSelect = ''
})
