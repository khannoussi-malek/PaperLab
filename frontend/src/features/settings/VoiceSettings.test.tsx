// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type VoiceLatency } from '@/api/client'
import { VoiceSettings } from './VoiceSettings'

afterEach(() => vi.restoreAllMocks())

const none = { n: 0, median: null, p90: null, p95: null, p99: null }
const stage = (n: number, median: number | null) => ({ ...none, n, median })
const empty = {
  wait_ms: none, stt_ms: none, retrieval_ms: none, embed_ms: none, ttft_ms: none,
  first_chunk_ms: none, tts_first_ms: none, output_ms: none, total_ms: none, interrupt_stop_ms: none,
}
const latency = (groups: VoiceLatency['groups']): VoiceLatency => ({ groups })
const ready = { ready: true, detail: null }

function show(status: { ready: boolean; detail: string | null }, data: VoiceLatency) {
  vi.spyOn(api, 'voiceStatus').mockResolvedValue(status)
  vi.spyOn(api, 'voiceLatency').mockResolvedValue(data)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <VoiceSettings />
    </QueryClientProvider>,
  )
}

test('no turns invites a question out loud', async () => {
  show(ready, latency([]))
  expect(await screen.findByText('Ask a question out loud to see numbers here.')).toBeInTheDocument()
})

test('a program that is not ready shows why and the command', async () => {
  show({ ready: false, detail: "The voice program isn't running. Start it with scripts/voice.sh." }, latency([]))
  expect(await screen.findByText("The voice program isn't running. Start it with scripts/voice.sh.")).toBeInTheDocument()
})

test('a ready program says so', async () => {
  show(ready, latency([]))
  expect(await screen.findByText('The voice program is ready.')).toBeInTheDocument()
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
  expect(
    screen.getByText("Times are from this computer. Each stage is its own median, so they won't add up to the total."),
  ).toBeInTheDocument()
})

test('needs-10-turns shows for a stage with too few turns', async () => {
  const warm = { ...empty, stt_ms: stage(3, 400) }
  show(ready, latency([{ model: 'qwen', warm, cold: empty, interrupts: 0, false_interrupts: 0 }]))
  const row = (await screen.findByText('Speech to text')).closest('tr')!
  expect(within(row).getByText('needs 10 turns')).toBeInTheDocument()
})
