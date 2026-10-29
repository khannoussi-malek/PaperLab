// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { DeskStage } from './DeskStage'

vi.mock('./TriageCard', () => ({
  TriageCard: ({ paper }: { paper: Paper }) => (
    <article data-triage-card><h2>{paper.title}</h2><button>Show</button><div aria-label="Abstract">abs</div></article>
  ),
}))

beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanup(); vi.useRealTimers() })

const paper = (id: string) => ({ id, title: `Paper ${id}` }) as unknown as Paper
const counts = { read_closely: 3, skim: 2, later: 1, not_relevant: 4, skip: 0 }
const base = {
  top: paper('a'), behind: [paper('b'), paper('c')], counts, layout: 'wide' as const, hot: null, hovering: null,
  departing: null, onCommit: vi.fn(), onHover: vi.fn(), reduced: false,
}
const show = (extra: Partial<Parameters<typeof DeskStage>[0]> = {}) => render(<DeskStage {...base} {...extra} />)

it('renders four targets with key, count and a name for assistive tech', () => {
  show()
  expect(document.querySelectorAll('[data-triage-target]')).toHaveLength(4)
  const t = screen.getByRole('button', { name: 'Not relevant, key 4' })
  expect(t).toHaveAttribute('data-triage-target', 'not_relevant')
  expect(t).toHaveTextContent('4')
  expect(screen.getByRole('button', { name: 'Read closely, key 1' })).toHaveTextContent('3')
})

it('clicking a target commits its pile', () => {
  const onCommit = vi.fn()
  show({ onCommit })
  fireEvent.click(screen.getByRole('button', { name: 'Later, key 3' }))
  expect(onCommit).toHaveBeenCalledWith('later')
})

it('a drag past 80 px on the card commits, and shows an aria-hidden stamp with the pile label while dragging', () => {
  const onCommit = vi.fn()
  show({ onCommit })
  const el = screen.getByRole('heading')
  fireEvent.pointerDown(el, { clientX: 0, clientY: 0, pointerId: 1, button: 0 })
  fireEvent.pointerMove(el, { clientX: 120, clientY: 0, pointerId: 1 })
  const stamp = document.querySelector('[data-triage-stamp]')!
  expect(stamp).toHaveAttribute('aria-hidden', 'true')
  expect(stamp).toHaveTextContent('Read closely')
  fireEvent.pointerUp(el, { clientX: 120, clientY: 0, pointerId: 1 })
  expect(onCommit).toHaveBeenCalledWith('read_closely')
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
})

it('a held pile key shows its stamp', () => {
  show({ hot: 'skim' })
  expect(document.querySelector('[data-triage-stamp]')).toHaveTextContent('Skim')
})

it('draws up to two decorative edges behind the card', () => {
  show()
  const edges = document.querySelectorAll('[data-triage-edge]')
  expect(edges).toHaveLength(2)
  edges.forEach((e) => { expect(e).toHaveAttribute('aria-hidden', 'true'); expect(e).toBeEmptyDOMElement() })
})

it('single layout is the card alone: no targets, no drag', () => {
  const onCommit = vi.fn()
  show({ layout: 'single', onCommit })
  expect(document.querySelector('[data-triage-target]')).toBeNull()
  expect(document.querySelector('[data-triage-edge]')).toBeNull()
  const el = screen.getByRole('heading')
  fireEvent.pointerDown(el, { clientX: 0, clientY: 0, pointerId: 1, button: 0 })
  fireEvent.pointerUp(el, { clientX: 200, clientY: 0, pointerId: 1 })
  expect(onCommit).not.toHaveBeenCalled()
})

it('tabs layout keeps the targets as corner labels', () => {
  show({ layout: 'tabs' })
  expect(document.querySelectorAll('[data-triage-target]')).toHaveLength(4)
})

it('reduced motion renders no clone and no fan edges', () => {
  show({ reduced: true, departing: { pile: 'skim' } })
  expect(document.querySelector('[data-triage-departing]')).toBeNull()
  expect(document.querySelector('[data-triage-edge]')).toBeNull()
})

it('departing renders an inert clone for 220 ms and a second commit is never held up', () => {
  const onCommit = vi.fn()
  const { rerender } = render(<DeskStage {...base} onCommit={onCommit} />)
  rerender(<DeskStage {...base} onCommit={onCommit} departing={{ pile: 'skim' }} />)
  const clone = document.querySelector('[data-triage-departing]')!
  expect(clone).toHaveAttribute('aria-hidden', 'true')
  expect(clone).toHaveAttribute('inert')
  fireEvent.click(screen.getByRole('button', { name: 'Skim, key 2' }))
  expect(onCommit).toHaveBeenCalledWith('skim')
  act(() => { vi.advanceTimersByTime(220) })
  expect(document.querySelector('[data-triage-departing]')).toBeNull()
})

it('two departures 50 ms apart are two clones, each gone 220 ms after its own start', () => {
  const { rerender } = render(<DeskStage {...base} />)
  rerender(<DeskStage {...base} departing={{ pile: 'skim' }} />)
  act(() => { vi.advanceTimersByTime(50) })
  rerender(<DeskStage {...base} departing={{ pile: 'later' }} />)
  expect(document.querySelectorAll('[data-triage-departing]')).toHaveLength(2)
  act(() => { vi.advanceTimersByTime(170) })
  expect(document.querySelectorAll('[data-triage-departing]')).toHaveLength(1)
  act(() => { vi.advanceTimersByTime(50) })
  expect(document.querySelectorAll('[data-triage-departing]')).toHaveLength(0)
})

it('a reset to null or a reduced flip mid-flight still removes the clone', () => {
  const { rerender } = render(<DeskStage {...base} />)
  rerender(<DeskStage {...base} departing={{ pile: 'skim' }} />)
  rerender(<DeskStage {...base} departing={null} reduced />)
  act(() => { vi.advanceTimersByTime(220) })
  expect(document.querySelector('[data-triage-departing]')).toBeNull()
})

it('the clone sits in the light paper scope', () => {
  const { rerender } = render(<DeskStage {...base} />)
  rerender(<DeskStage {...base} departing={{ pile: 'skim' }} />)
  expect(document.querySelector('[data-triage-departing]')).toHaveClass('paper-surface')
})
