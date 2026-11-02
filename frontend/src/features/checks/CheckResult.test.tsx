// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { ChatSource } from '@/api/client'
import { CheckResult } from './CheckResult'

const source = { label: 'C1', page: 4, section: 'Method', from_abstract: false, bbox: [], paper_id: 'p1' } as unknown as ChatSource
const base = {
  label: 'summary', lines: [], dropped: 0, sources: [source], tooltip: 'AI · m · check prompt v1 · 3 passages',
  stale: false, busy: false, onCheckAgain: vi.fn(), onCite: vi.fn(),
}
const lines = [
  { verdict: 'missing' as const, text: 'It never says what the loss is [C1].' },
  { verdict: 'unsupported' as const, text: 'Claims 10x speed.' },
  { verdict: 'supported' as const, text: 'Uses attention.' },
]

test('names the block and shows each verdict as a word', () => {
  render(<CheckResult {...base} lines={lines} />)
  const block = screen.getByRole('region', { name: 'Check of your summary' })
  expect(within(block).getByText('Missing')).toBeInTheDocument()
  expect(within(block).getByText('Unsupported')).toBeInTheDocument()
  expect(within(block).getByText('Supported')).toBeInTheDocument()
  expect(block.querySelectorAll('.check-line')).toHaveLength(3)
  expect(block.querySelector('.check-line')).toHaveAttribute('data-verdict', 'missing')
  expect(screen.getByText('AI · m · check prompt v1 · 3 passages')).toBeInTheDocument()
})

test('a citation is named in words and a click calls onCite', () => {
  const onCite = vi.fn()
  render(<CheckResult {...base} lines={lines} onCite={onCite} />)
  fireEvent.click(screen.getByRole('button', { name: /Source 1: page 4/ }))
  expect(onCite).toHaveBeenCalledWith(source)
})

test('an unknown [C9] stays text', () => {
  render(<CheckResult {...base} lines={[{ verdict: 'missing', text: 'Odd [C9].' }]} />)
  expect(screen.getByText(/Odd \[C9\]\./)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /\[C9\]/ })).toBeNull()
})

test('no lines', () => {
  render(<CheckResult {...base} />)
  expect(screen.getByText('No gaps found in the passages it read.')).toBeInTheDocument()
})

test('dropped lines, singular and plural', () => {
  const { rerender } = render(<CheckResult {...base} lines={lines} dropped={1} />)
  expect(screen.getByText("1 line of the reply didn't follow the check's format and was left out.")).toBeInTheDocument()
  rerender(<CheckResult {...base} lines={lines} dropped={2} />)
  expect(screen.getByText("2 lines of the reply didn't follow the check's format and were left out.")).toBeInTheDocument()
})

test('every line dropped', () => {
  render(<CheckResult {...base} dropped={3} />)
  expect(screen.getByText("The reply didn't follow the check's format, so nothing is shown. Check again, or pick another model in Chat.")).toBeInTheDocument()
  expect(screen.queryByText('No gaps found in the passages it read.')).toBeNull()
})

test('stale: dimmed, lines stay, primary Check again', () => {
  const onCheckAgain = vi.fn()
  render(<CheckResult {...base} lines={lines} stale onCheckAgain={onCheckAgain} />)
  expect(screen.getByText('Out of date: you changed this note after the check.')).toHaveClass('check-stale')
  expect(screen.getByRole('region')).toHaveClass('opacity-70')
  expect(screen.getAllByText('Missing')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(onCheckAgain).toHaveBeenCalled()
})

test('offers nothing to save, copy or insert', () => {
  render(<CheckResult {...base} lines={lines} />)
  const names = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label') ?? b.textContent)
  expect(names.every((n) => /^Source 1|^Check again$/.test(n ?? ''))).toBe(true)
  expect(screen.queryByRole('button', { name: /save|copy|insert/i })).toBeNull()
})
