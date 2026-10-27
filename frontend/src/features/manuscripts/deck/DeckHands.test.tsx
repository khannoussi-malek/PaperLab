// @vitest-environment jsdom
import { act, fireEvent, render } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const hm = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }))
vi.mock('../../graph/hands/HandsMode', () => ({ default: (p: Record<string, unknown>) => { hm.props = p; return null } }))

import { DeckHands, TYPING_PAUSE_MS } from './DeckHands'

function Host({ onAction = vi.fn(), onSelect = vi.fn() }) {
  const column = useRef<HTMLDivElement>(null)
  return (
    <div>
      <textarea data-testid="editor" />
      <div ref={column}>
        <button data-testid="inside">x</button>
        <div data-deck-card="p1" aria-label="Alpha" />
        <DeckHands column={column} onAction={onAction} onSelect={onSelect} />
      </div>
    </div>
  )
}
const paused = () => hm.props!.paused as boolean

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

it('is paused until focus or the pointer is in the deck column', () => {
  const { getByTestId } = render(<Host />)
  expect(paused()).toBe(true)
  fireEvent.focusIn(getByTestId('inside'))
  expect(paused()).toBe(false)
  fireEvent.focusIn(getByTestId('editor'))
  expect(paused()).toBe(true)
  fireEvent.pointerOver(getByTestId('inside'))
  expect(paused()).toBe(false)
})

it('is paused for 2 s after a keystroke anywhere, then resumes', () => {
  const { getByTestId } = render(<Host />)
  fireEvent.focusIn(getByTestId('inside'))
  fireEvent.keyDown(getByTestId('editor'), { key: 'a' })
  expect(paused()).toBe(true)
  act(() => { vi.advanceTimersByTime(TYPING_PAUSE_MS - 1) })
  expect(paused()).toBe(true)
  fireEvent.keyDown(document.body, { key: 'b' }) // a new key restarts the wait
  act(() => { vi.advanceTimersByTime(TYPING_PAUSE_MS - 1) })
  expect(paused()).toBe(true)
  act(() => { vi.advanceTimersByTime(1) })
  expect(paused()).toBe(false)
})

it('maps hand callbacks to deck actions and holds to card or tab selects', () => {
  const onAction = vi.fn()
  const onSelect = vi.fn()
  render(<Host onAction={onAction} onSelect={onSelect} />)
  const p = hm.props as { onHop: (n: number) => void; onZoom: (f: number) => void; onTurn: (a: number) => void; onSelect: (id: string) => void }
  p.onHop(1)
  p.onZoom(1.3)
  p.onTurn(0.4)
  p.onSelect('p1')
  expect(onAction.mock.calls.map((c) => c[0])).toEqual([{ type: 'step', by: 1 }, { type: 'open' }, { type: 'step', by: 1 }])
  expect(onSelect).toHaveBeenCalledWith('p1', 'card')
})
