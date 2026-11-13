// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type VoiceLatency, type VoiceStatus } from '@/api/client'
import { VoiceSettings } from './VoiceSettings'
import type { VoiceBridge } from './desktop'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const none = { n: 0, median: null, p90: null, p95: null, p99: null }
const stage = (n: number, median: number | null) => ({ ...none, n, median })
const empty = {
  wait_ms: none, stt_ms: none, retrieval_ms: none, embed_ms: none, ttft_ms: none,
  first_chunk_ms: none, tts_first_ms: none, output_ms: none, total_ms: none, interrupt_stop_ms: none,
}
const latency = (groups: VoiceLatency['groups']): VoiceLatency => ({ groups })
const ready = { ready: true, stage: 'ready' as const, detail: null }
const off = { ready: false, stage: 'off' as const, detail: null }

function voiceBridge(over: Partial<VoiceBridge> = {}): VoiceBridge {
  return {
    getVoiceEnabled: vi.fn(async () => false),
    setVoiceEnabled: vi.fn(async () => ({ ok: true, detail: null })),
    onVoiceProgress: vi.fn(() => () => {}),
    removeVoiceModels: vi.fn(async () => ({ ok: true, detail: null })),
    voiceOutOfMemory: vi.fn(async () => false),
    ...over,
  }
}

function show(status: VoiceStatus, data: VoiceLatency = latency([]), bridge?: VoiceBridge) {
  vi.spyOn(api, 'voiceStatus').mockResolvedValue(status)
  vi.spyOn(api, 'voiceLatency').mockResolvedValue(data)
  if (bridge) vi.stubGlobal('paperlabDesktop', bridge)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <VoiceSettings />
    </QueryClientProvider>,
  )
}

test('no turns invites a question out loud', async () => {
  show(ready)
  expect(await screen.findByText('Ask a question out loud to see numbers here.')).toBeInTheDocument()
})

test('the stage message says voice is off when it is off', async () => {
  show(off)
  expect(await screen.findByText('Voice is off.')).toBeInTheDocument()
})

test('with the switch on but the program not running, it says so instead of "Voice is off."', async () => {
  show(off, latency([]), voiceBridge({ getVoiceEnabled: vi.fn(async () => true) }))
  expect(await screen.findByText("Voice isn't running yet. If this lasts, turn voice off and on again.")).toBeInTheDocument()
  expect(screen.queryByText('Voice is off.')).not.toBeInTheDocument()
})

test('an off program shows its own detail, unless the detail is the API default', async () => {
  show({ ready: false, stage: 'off', detail: 'The reply was not understood.' })
  expect(await screen.findByText('The reply was not understood.')).toBeInTheDocument()
})

test('an off program with the API default detail still says voice is off', async () => {
  show({ ready: false, stage: 'off', detail: 'Voice is off. Turn it on in Settings → Voice.' })
  expect(await screen.findByText('Voice is off.')).toBeInTheDocument()
})

test('a failed program with an empty detail shows the fallback, not a blank line', async () => {
  show({ ready: false, stage: 'failed', detail: '' })
  expect(await screen.findByText('Voice failed to start.')).toBeInTheDocument()
})

test('a ready program says so', async () => {
  show(ready)
  expect(await screen.findByText('Voice is ready.')).toBeInTheDocument()
})

test('a failed program shows its detail', async () => {
  show({ ready: false, stage: 'failed', detail: 'The speech model could not be checked.' })
  expect(await screen.findByText('The speech model could not be checked.')).toBeInTheDocument()
})

test('downloading and loading say what is happening', async () => {
  show({ ready: false, stage: 'downloading', detail: null })
  expect(await screen.findByText('Getting voice ready: downloading the speech models.')).toBeInTheDocument()
})

test('the table shows each stage with its count and median, and what lacks turns', async () => {
  const warm = { ...empty, stt_ms: { n: 12, median: 410, p90: 800, p95: null, p99: null }, total_ms: stage(12, 2300) }
  show(ready, latency([{ model: 'qwen', warm, cold: empty, interrupts: 12, false_interrupts: 1 }]))

  const row = (await screen.findByText('Speech to text')).closest('tr')!
  expect(within(row).getByText('12')).toBeInTheDocument()
  expect(within(row).getByText('410 ms')).toBeInTheDocument()
  expect(within(row).getByText('800 ms')).toBeInTheDocument()
  expect(within(row).getAllByText('needs 20 turns').length).toBe(1)
  expect(screen.getByText('Stop talking to first audio')).toBeInTheDocument()
  expect(screen.getByText('12 interruptions, 1 probably false')).toBeInTheDocument()
  expect(screen.getByText('Waiting for silence (a setting)')).toBeInTheDocument()
  const note = screen.getByText(/^Times are from this computer\./)
  expect(note).toHaveTextContent("Each stage is its own median, so they won't add up to the total.")
  expect(note).toHaveTextContent("Stopping when interrupted includes the 250 ms it waits to be sure you're speaking.")
  expect(note).toHaveTextContent('From your latest 500 voice questions.')
})

test('needs-10-turns shows for a stage with too few turns', async () => {
  const warm = { ...empty, stt_ms: stage(3, 400) }
  show(ready, latency([{ model: 'qwen', warm, cold: empty, interrupts: 0, false_interrupts: 0 }]))
  const row = (await screen.findByText('Speech to text')).closest('tr')!
  expect(within(row).getByText('needs 10 turns')).toBeInTheDocument()
})

test('one interruption is singular', async () => {
  show(ready, latency([{ model: 'qwen', warm: { ...empty, stt_ms: stage(3, 400) }, cold: empty, interrupts: 1, false_interrupts: 0 }]))
  expect(await screen.findByText('1 interruption, 0 probably false')).toBeInTheDocument()
})

test('the first question after turning the microphone on has its own table', async () => {
  const cold = { ...empty, stt_ms: stage(2, 900) }
  show(ready, latency([{ model: 'qwen', warm: empty, cold, interrupts: 0, false_interrupts: 0 }]))
  expect(await screen.findByText('First question after turning the microphone on')).toBeInTheDocument()
  expect(screen.queryByText(/after the voice program started/)).not.toBeInTheDocument()
})

test('with a voice bridge it shows the switch with its label and help', async () => {
  show(off, latency([]), voiceBridge())
  const sw = await screen.findByRole('switch', { name: 'Ask questions out loud' })
  expect(sw).toHaveAttribute('aria-checked', 'false')
  expect(screen.getByText(/Turns your speech into text and reads answers aloud, all on this computer\./)).toBeInTheDocument()
  expect(screen.queryByText(/docker compose --profile voice/)).not.toBeInTheDocument()
})

test('without a voice bridge it shows the compose line instead of a switch', async () => {
  show(off)
  const line = await screen.findByText(/To use voice, run/)
  expect(line).toHaveTextContent('To use voice, run docker compose --profile voice up -d in your PaperLab folder.')
  expect(line.querySelector('code')).toHaveTextContent('docker compose --profile voice up -d')
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
})

test('turning on shows the latest progress line, then the stage', async () => {
  let progress: (line: string) => void = () => {}
  let finish: (value: { ok: boolean; detail: string | null }) => void = () => {}
  const bridge = voiceBridge({
    onVoiceProgress: vi.fn((cb) => {
      progress = cb
      return () => {}
    }),
    setVoiceEnabled: vi.fn(() => new Promise<{ ok: boolean; detail: string | null }>((resolve) => (finish = resolve))),
  })
  show(off, latency([]), bridge)
  fireEvent.click(await screen.findByRole('switch', { name: 'Ask questions out loud' }))
  expect(screen.getByRole('switch', { name: 'Ask questions out loud' })).toBeChecked()

  progress('Downloading model 1 of 2')
  progress('Downloading model 2 of 2')
  expect(await screen.findByText('Downloading model 2 of 2')).toBeInTheDocument()
  expect(screen.queryByText('Downloading model 1 of 2')).not.toBeInTheDocument()
  finish({ ok: true, detail: null })
  await waitFor(() => expect(bridge.setVoiceEnabled).toHaveBeenCalledWith(true))
})

test('the switch is disabled while voice is being turned on', async () => {
  let finish: (value: { ok: boolean; detail: string | null }) => void = () => {}
  const bridge = voiceBridge({
    setVoiceEnabled: vi.fn(() => new Promise<{ ok: boolean; detail: string | null }>((resolve) => (finish = resolve))),
  })
  show(off, latency([]), bridge)
  fireEvent.click(await screen.findByRole('switch', { name: 'Ask questions out loud' }))
  expect(screen.getByRole('switch', { name: 'Ask questions out loud' })).toBeDisabled()
  finish({ ok: true, detail: null })
  await waitFor(() => expect(screen.getByRole('switch', { name: 'Ask questions out loud' })).toBeEnabled())
})

test('a failed set with an empty detail shows the fallback', async () => {
  const bridge = voiceBridge({ setVoiceEnabled: vi.fn(async () => ({ ok: false, detail: '' })) })
  show(off, latency([]), bridge)
  fireEvent.click(await screen.findByRole('switch', { name: 'Ask questions out loud' }))
  expect(await screen.findByRole('alert')).toHaveTextContent("Voice didn't turn on. Try again.")
})

test('a failed set shows its detail and the switch stays off', async () => {
  const bridge = voiceBridge({
    setVoiceEnabled: vi.fn(async () => ({ ok: false, detail: 'Docker is not running.' })),
  })
  show(off, latency([]), bridge)
  fireEvent.click(await screen.findByRole('switch', { name: 'Ask questions out loud' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Docker is not running.')
  expect(screen.getByRole('switch', { name: 'Ask questions out loud' })).not.toBeChecked()
})

test('out_of_memory_message: says Docker ran out of memory when the program was killed for it', async () => {
  show(off, latency([]), voiceBridge({ voiceOutOfMemory: vi.fn(async () => true) }))
  expect(
    await screen.findByText(
      'Docker ran out of memory for voice. Give Docker more memory in its settings, then turn voice off and on.',
    ),
  ).toBeInTheDocument()
})

test('the out-of-memory message stays hidden while voice is ready', async () => {
  show(ready, latency([]), voiceBridge({ voiceOutOfMemory: vi.fn(async () => true) }))
  await screen.findByText('Voice is ready.')
  expect(screen.queryByText(/Docker ran out of memory/)).not.toBeInTheDocument()
})

test('Remove voice models shows only while the switch is off', async () => {
  show(off, latency([]), voiceBridge())
  expect(await screen.findByRole('button', { name: 'Remove voice models' })).toBeInTheDocument()
})

test('Remove voice models is hidden while the switch is on', async () => {
  show(ready, latency([]), voiceBridge({ getVoiceEnabled: vi.fn(async () => true) }))
  await screen.findByRole('switch', { name: 'Ask questions out loud' })
  await waitFor(() => expect(screen.getByRole('switch', { name: 'Ask questions out loud' })).toBeChecked())
  expect(screen.queryByRole('button', { name: 'Remove voice models' })).not.toBeInTheDocument()
})

test('a failed remove shows its detail', async () => {
  show(off, latency([]), voiceBridge({ removeVoiceModels: vi.fn(async () => ({ ok: false, detail: 'The models are in use.' })) }))
  fireEvent.click(await screen.findByRole('button', { name: 'Remove voice models' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The models are in use.')
})
