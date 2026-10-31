// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { REASONS } from './piles'
import { ReasonChips } from './ReasonChips'

afterEach(cleanup)
const show = () => {
  const onPick = vi.fn(), onCancel = vi.fn()
  render(<ReasonChips reasons={REASONS.not_relevant} onPick={onPick} onCancel={onCancel} noteFor="other" />)
  return { onPick, onCancel }
}

it('is a group named Reason with numbered chips', () => {
  show()
  const group = screen.getByRole('group', { name: 'Reason' })
  const labels = [...group.querySelectorAll('[data-reason-chip]')].map((b) => b.textContent)
  expect(labels).toEqual(['1 off-topic', '2 wrong method', '3 low quality', '4 duplicate', '5 already known', '6 other…'])
})

it('a chip picks its reason without a note', () => {
  const { onPick } = show()
  fireEvent.click(screen.getByRole('button', { name: '1 off-topic' }))
  expect(onPick).toHaveBeenCalledWith('off_topic', undefined)
})

it('other opens a one-line note; Enter commits with or without text', () => {
  const { onPick } = show()
  fireEvent.click(screen.getByRole('button', { name: '6 other…' }))
  expect(onPick).not.toHaveBeenCalled()
  const note = screen.getByRole('textbox', { name: 'Note' })
  expect(note).toHaveFocus()
  fireEvent.change(note, { target: { value: '  sounds off  ' } })
  fireEvent.keyDown(note, { key: 'Enter' })
  expect(onPick).toHaveBeenCalledWith('other', 'sounds off')
})

it('other with an empty note still commits on Enter', () => {
  const { onPick } = show()
  fireEvent.click(screen.getByRole('button', { name: '6 other…' }))
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Note' }), { key: 'Enter' })
  expect(onPick).toHaveBeenCalledWith('other', undefined)
})

it('Esc in the note cancels', () => {
  const { onPick, onCancel } = show()
  fireEvent.click(screen.getByRole('button', { name: '6 other…' }))
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Note' }), { key: 'Escape' })
  expect(onCancel).toHaveBeenCalledTimes(1)
  expect(onPick).not.toHaveBeenCalled()
})
