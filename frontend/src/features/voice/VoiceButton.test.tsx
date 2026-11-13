// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type VoiceStatus } from '@/api/client'
import type { useVoiceTurn } from './useVoiceTurn'
import { VoiceButton } from './VoiceButton'

afterEach(() => vi.restoreAllMocks())

type Voice = ReturnType<typeof useVoiceTurn>
const voice = (over: Partial<Voice> = {}): Voice =>
  ({ on: false, state: 'off', stream: { status: 'idle' }, problem: null, start: vi.fn(), stop: vi.fn(), ...over }) as unknown as Voice

function renderWith(status: VoiceStatus, ui: (props: { voice: Voice }) => React.ReactElement, v: Voice) {
  vi.spyOn(api, 'voiceStatus').mockResolvedValue(status)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const tree = (value: Voice) => (
    <QueryClientProvider client={client}>{ui({ voice: value })}</QueryClientProvider>
  )
  return render(tree(v))
}

const ready: VoiceStatus = { ready: true, stage: 'ready', detail: null }

it('is an off toggle that starts listening when pressed', async () => {
  const v = voice()
  renderWith(ready, (p) => <VoiceButton {...p} />, v)
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toBeEnabled())
  expect(button).toHaveAttribute('aria-pressed', 'false')
  expect(screen.queryByText('Listening')).not.toBeInTheDocument()
  fireEvent.click(button)
  expect(v.start).toHaveBeenCalled()
})

it.each([
  ['listening', 'Listening, press to turn off'],
  ['thinking', 'Thinking, press to turn off'],
  ['speaking', 'Speaking, press to turn off'],
] as const)('says %s, shows that the mic is open, and turns it off when pressed', async (state, label) => {
  const v = voice({ on: true, state })
  renderWith(ready, (p) => <VoiceButton {...p} />, v)
  const button = await screen.findByRole('button', { name: label })
  expect(button).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('Listening')).toBeVisible()
  fireEvent.click(button)
  expect(v.stop).toHaveBeenCalled()
})

it('says the microphone is starting, is pressed, and turns off when pressed', async () => {
  const v = voice({ on: true, state: 'starting' })
  renderWith(ready, (p) => <VoiceButton {...p} />, v)
  const button = await screen.findByRole('button', { name: 'Starting the microphone' })
  expect(button).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(button)
  expect(v.stop).toHaveBeenCalled()
  expect(v.start).not.toHaveBeenCalled()
})

it('cannot be started while typed chat is busy, but can always be turned off', async () => {
  const { rerender } = renderWith(ready, (p) => <VoiceButton {...p} disabled />, voice())
  await waitFor(() => expect(screen.getByRole('button', { name: 'Ask out loud' })).toBeDisabled())
  expect(screen.getByRole('button', { name: 'Ask out loud' })).toBeDisabled()
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <VoiceButton voice={voice({ on: true, state: 'listening' })} disabled />
    </QueryClientProvider>,
  )
  expect(await screen.findByRole('button', { name: 'Listening, press to turn off' })).toBeEnabled()
})

it.each([
  ['off', "Voice isn't running. Turn it on in Settings → Voice."],
  ['downloading', 'Voice is getting ready'],
  ['loading', 'Voice is getting ready'],
] as const)('is disabled with a tooltip while the stage is %s', async (stage, tooltip) => {
  renderWith({ ready: false, stage, detail: null }, (p) => <VoiceButton {...p} />, voice())
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toHaveAttribute('title', tooltip))
  expect(button).toBeDisabled()
})

it("is disabled with the program's detail as the tooltip when it failed", async () => {
  renderWith({ ready: false, stage: 'failed', detail: 'The speech model could not be checked.' }, (p) => <VoiceButton {...p} />, voice())
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toHaveAttribute('title', 'The speech model could not be checked.'))
  expect(button).toBeDisabled()
})

it("says the status is unavailable when the status read fails", async () => {
  vi.spyOn(api, 'voiceStatus').mockRejectedValue(new Error('network down'))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <VoiceButton voice={voice()} />
    </QueryClientProvider>,
  )
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toHaveAttribute('title', 'Voice status unavailable. Try again in a moment.'))
  expect(button).toBeDisabled()
})

it('a failed program with an empty detail gets the fallback tooltip', async () => {
  renderWith({ ready: false, stage: 'failed', detail: '' }, (p) => <VoiceButton {...p} />, voice())
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toHaveAttribute('title', 'Voice failed to start.'))
})

it('is enabled and has no tooltip when ready', async () => {
  renderWith(ready, (p) => <VoiceButton {...p} />, voice())
  const button = await screen.findByRole('button', { name: 'Ask out loud' })
  await waitFor(() => expect(button).toBeEnabled())
  expect(button).not.toHaveAttribute('title')
})
