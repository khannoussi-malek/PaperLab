// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { DeskStatus, TriageControls } from './TriageControls'

afterEach(cleanup)
const props = (over = {}) => ({
  layout: 'wide' as const,
  undo: null, onUndo: vi.fn(), onDecide: vi.fn(),
  progress: { decided: 46, skipped: 3, total: 60 },
  ...over,
})

it('shows the four piles with key hints, Skip, and progress as text and as a progressbar', () => {
  const p = props(); render(<TriageControls {...p} />)
  expect(screen.getByRole('button', { name: /Read closely/ })).toHaveTextContent('1')
  expect(screen.getByRole('button', { name: /Skim/ })).toHaveTextContent('2')
  expect(screen.getByRole('button', { name: /Later/ })).toHaveTextContent('3')
  expect(screen.getByRole('button', { name: /Not relevant/ })).toHaveTextContent('4')
  expect(screen.getByRole('button', { name: /Skip/ })).toHaveTextContent('Space')
  const bar = screen.getByRole('progressbar')
  expect(bar).toHaveAttribute('aria-valuenow', '46')
  expect(bar).toHaveAttribute('aria-valuemax', '60')
  expect(screen.getByText('46 of 60 decided this session · 3 skipped')).toBeInTheDocument()
})

it('no skipped part while nothing is skipped', () => {
  render(<TriageControls {...props({ progress: { decided: 0, skipped: 0, total: 5 } })} />)
  expect(screen.getByText('0 of 5 decided this session')).toBeInTheDocument()
})

it('Undo is disabled and says so when empty, and names the last decision when not', () => {
  const { unmount } = render(<TriageControls {...props()} />)
  expect(screen.getByRole('button', { name: 'Nothing to undo' })).toBeDisabled()
  unmount()
  const p = props({ undo: { label: "Skim 'Lewis 2020'", count: 3 } }); render(<TriageControls {...p} />)
  const b = screen.getByRole('button', { name: /Undo: Skim 'Lewis 2020'/ })
  expect(b).toHaveTextContent('3')
  fireEvent.click(b)
  expect(p.onUndo).toHaveBeenCalledTimes(1)
})

it('a decision button decides its pile; Skip decides skip', () => {
  const p = props(); render(<TriageControls {...p} />)
  fireEvent.click(screen.getByRole('button', { name: /Later/ }))
  fireEvent.click(screen.getByRole('button', { name: /Skip/ }))
  expect(p.onDecide.mock.calls).toEqual([['later'], ['skip']])
})

it('single layout hides key hints and makes the buttons 44px stacked', () => {
  render(<TriageControls {...props({ layout: 'single' })} />)
  const b = screen.getByRole('button', { name: 'Read closely' })
  expect(b).not.toHaveTextContent('1')
  expect(b.className).toContain('min-h-11')
  expect(screen.getByRole('group', { name: 'Decide' })).toHaveClass('flex-col')
})

it('the status shows the announcement politely and the failure strip with Retry', () => {
  const retry = vi.fn()
  render(<DeskStatus announcement="Skim. 3 of 9 done." alert={{ message: "Couldn't save: boom", retry }} />)
  expect(screen.getByText('Skim. 3 of 9 done.').closest('[aria-live]')).toHaveAttribute('aria-live', 'polite')
  expect(screen.getByRole('alert')).toHaveTextContent("Couldn't save: boom")
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(retry).toHaveBeenCalled()
})

it('no alert strip and no Retry when there is none to offer', () => {
  const { rerender } = render(<DeskStatus announcement="" alert={null} />)
  expect(screen.queryByRole('alert')).toBeNull()
  rerender(<DeskStatus announcement="" alert={{ message: 'changed elsewhere' }} />)
  expect(screen.getByRole('alert')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
})
