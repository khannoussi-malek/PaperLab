// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type ChatModel } from '@/api/client'

const mocks = vi.hoisted(() => ({
  startMicrophone: vi.fn(),
  playback: { play: vi.fn(), stop: vi.fn(), active: vi.fn(() => false), playedSeconds: vi.fn(() => 0) },
}))
vi.mock('@/features/voice/microphone', () => ({ startMicrophone: mocks.startMicrophone }))
vi.mock('@/features/voice/playback', () => ({ createPlayback: () => mocks.playback }))

import { ChatPanel } from './ChatPanel'

class FakeSocket {
  static last: FakeSocket
  onopen: (() => void) | null = null
  onmessage: ((e: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  binaryType = ''
  constructor() {
    FakeSocket.last = this
    queueMicrotask(() => this.onopen?.())
  }
  send() {}
  close() {}
  say(message: Record<string, unknown>) {
    act(() => this.onmessage?.({ data: JSON.stringify(message) }))
  }
}
class FakeContext {
  currentTime = 0
  outputLatency = 0
  destination = {}
  resume = async () => {}
  close = async () => {}
}

const model = { id: 'm1', name: 'Local', connection_label: 'Ollama', is_default: true } as unknown as ChatModel

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(api, 'listChat').mockResolvedValue([])
  vi.spyOn(api, 'listChatModels').mockResolvedValue([model])
  vi.spyOn(api, 'voiceStatus').mockResolvedValue({ ready: true, detail: null })
  mocks.startMicrophone.mockResolvedValue({ stop: async () => {}, echoCancelled: true })
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('AudioContext', FakeContext)
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} })
  Element.prototype.scrollTo = () => {}
  Element.prototype.scrollIntoView = () => {}
})
afterEach(() => vi.unstubAllGlobals())

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ChatPanel scope={{ kind: 'paper', id: 'p1' }} onCite={vi.fn()} onPromoted={vi.fn()} />
    </QueryClientProvider>,
  )
}

it('lets the reader type again after the microphone is turned off in the middle of an answer', async () => {
  renderPanel()
  const question = await screen.findByLabelText('Question')
  await waitFor(() => expect(question).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Ask out loud' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Listening, press to turn off' }))
  // (turned off again at once; now the real case: a spoken question under way)
  fireEvent.click(await screen.findByRole('button', { name: 'Ask out loud' }))
  await screen.findByRole('button', { name: 'Listening, press to turn off' })
  const handlers = mocks.startMicrophone.mock.calls.at(-1)![0]
  act(() => handlers.onSpeechEnd(new Float32Array(16000)))
  FakeSocket.last.say({ type: 'turn', id: 'x', n: 1 })
  FakeSocket.last.say({ type: 'transcript', text: 'What is it?' })
  FakeSocket.last.say({ type: 'token', text: 'It is' })
  await waitFor(() => expect(question).toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: 'Thinking, press to turn off' }))
  await waitFor(() => expect(question).toBeEnabled())
})
