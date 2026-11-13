// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type ChatModel, type ChatScope, type Skill } from '@/api/client'

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
  vi.spyOn(api, 'listSkills').mockResolvedValue([])
  vi.spyOn(api, 'voiceStatus').mockResolvedValue({ ready: true, stage: 'ready', detail: null })
  mocks.startMicrophone.mockResolvedValue({ stop: async () => {}, echoCancelled: true })
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('AudioContext', FakeContext)
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} })
  Element.prototype.scrollTo = () => {}
  Element.prototype.scrollIntoView = () => {}
})
afterEach(() => vi.unstubAllGlobals())

function renderPanel(scope: ChatScope = { kind: 'paper', id: 'p1' }) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ChatPanel scope={scope} onCite={vi.fn()} onPromoted={vi.fn()} />
    </QueryClientProvider>,
  )
}

it('lets the reader type again after the microphone is turned off in the middle of an answer', async () => {
  renderPanel()
  const question = await screen.findByLabelText('Question')
  await waitFor(() => expect(question).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Ask out loud' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Listening, press to turn off' }))
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

it("offers voice in a paper's and a workspace's chat but not in a search hit's, which the voice server can't answer", async () => {
  const { unmount } = renderPanel({ kind: 'workspace', id: 'w1' })
  expect(await screen.findByRole('button', { name: 'Ask out loud' })).toBeInTheDocument()
  unmount()
  vi.mocked(api.voiceStatus).mockClear()
  renderPanel({ kind: 'hit', id: 'h1', workspaceId: 'w1' })
  await screen.findByRole('button', { name: 'Ask' })
  expect(screen.queryByRole('button', { name: 'Ask out loud' })).toBeNull()
  expect(api.voiceStatus).not.toHaveBeenCalled()
})

describe('skill picker', () => {
  const limits = { id: 'builtin:limits', label: 'Limits', is_paper_default: true, is_workspace_default: false } as unknown as Skill

  beforeEach(() => {
    vi.spyOn(api, 'listSkills').mockResolvedValue([limits])
    vi.spyOn(api, 'askChat').mockReturnValue(new Promise<Response>(() => {}))
  })

  it('preselects the default for a paper and sends its skill_id with the question', async () => {
    renderPanel()
    expect(await screen.findByRole('combobox', { name: 'Skill' })).toHaveTextContent('Limits')
    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'What is new?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(api.askChat).toHaveBeenCalledWith({ kind: 'paper', id: 'p1' }, 'What is new?', 'm1', null, 'builtin:limits', expect.anything())
  })

  it('sends No skill as null, and shows the picker in a workspace chat too', async () => {
    renderPanel({ kind: 'workspace', id: 'w1' })
    const picker = await screen.findByRole('combobox', { name: 'Skill' })
    expect(picker).toHaveTextContent('No skill')
    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'Compare them' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(api.askChat).toHaveBeenCalledWith({ kind: 'workspace', id: 'w1' }, 'Compare them', 'm1', null, null, expect.anything())
  })

  it('shows no picker in a search hit chat, and sends no skill_id', async () => {
    renderPanel({ kind: 'hit', id: 'h1', workspaceId: 'w1' })
    await screen.findByRole('button', { name: 'Ask' })
    expect(screen.queryByRole('combobox', { name: 'Skill' })).toBeNull()
  })
})
