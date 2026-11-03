// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { useVoiceTurn } from './useVoiceTurn'
import { VoiceButton } from './VoiceButton'

type Voice = ReturnType<typeof useVoiceTurn>
const voice = (over: Partial<Voice> = {}): Voice =>
  ({ on: false, state: 'off', stream: { status: 'idle' }, problem: null, start: vi.fn(), stop: vi.fn(), ...over }) as unknown as Voice

it('is an off toggle that starts listening when pressed', () => {
  const v = voice()
  render(<VoiceButton voice={v} />)
  const button = screen.getByRole('button', { name: 'Ask out loud' })
  expect(button).toHaveAttribute('aria-pressed', 'false')
  expect(screen.queryByText('Listening')).not.toBeInTheDocument()
  fireEvent.click(button)
  expect(v.start).toHaveBeenCalled()
})

it.each([
  ['listening', 'Listening, press to turn off'],
  ['thinking', 'Thinking, press to turn off'],
  ['speaking', 'Speaking, press to turn off'],
] as const)('says %s, shows that the mic is open, and turns it off when pressed', (state, label) => {
  const v = voice({ on: true, state })
  render(<VoiceButton voice={v} />)
  const button = screen.getByRole('button', { name: label })
  expect(button).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('Listening')).toBeVisible()
  fireEvent.click(button)
  expect(v.stop).toHaveBeenCalled()
})

it('cannot be started while typed chat is busy, but can always be turned off', () => {
  const { rerender } = render(<VoiceButton voice={voice()} disabled />)
  expect(screen.getByRole('button', { name: 'Ask out loud' })).toBeDisabled()
  rerender(<VoiceButton voice={voice({ on: true, state: 'listening' })} disabled />)
  expect(screen.getByRole('button', { name: 'Listening, press to turn off' })).toBeEnabled()
})
