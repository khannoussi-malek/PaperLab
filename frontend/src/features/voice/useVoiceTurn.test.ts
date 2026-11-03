// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type ChatScope } from '@/api/client'
import type { MicrophoneHandlers } from './microphone'

const mocks = vi.hoisted(() => ({
  startMicrophone: vi.fn(),
  micStop: vi.fn(async () => {}),
  playback: {
    play: vi.fn(),
    stop: vi.fn(),
    active: vi.fn(() => false),
    playedSeconds: vi.fn(() => 0),
  },
  onIdle: undefined as (() => void) | undefined,
  playedAt: 0,
}))
vi.mock('./microphone', () => ({ startMicrophone: mocks.startMicrophone }))
vi.mock('./playback', () => ({
  createPlayback: (_ctx: unknown, _out: unknown, onIdle?: () => void) => {
    mocks.onIdle = onIdle
    return mocks.playback
  },
}))

import { useVoiceTurn } from './useVoiceTurn'

const HEADPHONES = 'Use headphones to talk over answers. Without echo cancelling, the app would hear itself.'
const DROPPED = 'The voice connection dropped. Press the microphone to try again.'

class FakeSocket {
  static last: FakeSocket
  static count = 0
  static hold = false // true: the socket stays connecting until the test calls onopen
  sent: (string | ArrayBufferLike)[] = []
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((e: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  binaryType = ''
  url: string
  constructor(url: string) {
    this.url = url
    FakeSocket.last = this
    FakeSocket.count++
    if (!FakeSocket.hold) queueMicrotask(() => this.onopen?.())
  }
  send(data: string | ArrayBufferLike) {
    if (this.closed) throw new Error('sent after close')
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
  get json() {
    return this.sent.filter((d): d is string => typeof d === 'string').map((d) => JSON.parse(d) as Record<string, unknown>)
  }
  get utterances() {
    return this.sent.filter((d) => typeof d !== 'string')
  }
  say(message: Record<string, unknown>) {
    act(() => this.onmessage?.({ data: JSON.stringify(message) }))
  }
  audio(samples = new Float32Array(160)) {
    act(() => this.onmessage?.({ data: samples.buffer }))
  }
}

class FakeContext {
  static last: FakeContext
  constructor() {
    FakeContext.last = this
  }
  currentTime = 0
  outputLatency = 0.02
  destination = {}
  resume = vi.fn(async () => {})
  close = vi.fn(async () => {})
}

let now = 0
let handlers: MicrophoneHandlers
let queryClient: QueryClient
const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
const scope = { kind: 'paper', id: 'p1' } as const

beforeEach(() => {
  vi.clearAllMocks()
  now = 10000
  FakeSocket.count = 0
  FakeSocket.hold = false
  mocks.playback.active.mockReturnValue(false)
  mocks.playback.playedSeconds.mockReturnValue(0)
  mocks.playback.play.mockImplementation((_s, _r, onFirst?: (at: number) => void) => onFirst?.(10900))
  mocks.startMicrophone.mockImplementation(async (h: MicrophoneHandlers) => {
    handlers = h
    return { stop: mocks.micStop, echoCancelled: true }
  })
  queryClient = new QueryClient()
  vi.spyOn(queryClient, 'invalidateQueries')
  vi.spyOn(api, 'voiceStatus').mockResolvedValue({ ready: true, detail: null })
  vi.spyOn(performance, 'now').mockImplementation(() => now)
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('AudioContext', FakeContext)
})
afterEach(() => vi.unstubAllGlobals())

async function started(modelId: string | null = null) {
  const hook = renderHook(() => useVoiceTurn(scope, modelId), { wrapper })
  await act(async () => {
    await hook.result.current.start()
  })
  return { ...hook, socket: FakeSocket.last }
}

/** The reader asks a question; the server's turn, transcript, sources and first sentence answer it. */
function ask(socket: FakeSocket, n = 1) {
  act(() => {
    handlers.onSpeechStart()
    handlers.onSpeechEnd(new Float32Array(16000))
  })
  socket.say({ type: 'turn', id: 'x', n })
  socket.say({ type: 'transcript', text: 'What is it?' })
  socket.say({ type: 'sources', whole_paper: false, sources: [], notes: [], notes_used: null, notes_total: null })
}
function sentence(socket: FakeSocket, seq = 0, text = 'It is a thing.') {
  socket.say({ type: 'token', text })
  socket.say({ type: 'sentence', seq, text, rate: 24000 })
  socket.audio()
}

it('opens the socket with the scope and model, and listens', async () => {
  const { result, socket } = await started('m1')
  expect(socket.url).toMatch(/^wss?:\/\/.+\/api\/voice\/ws$/)
  expect(socket.json[0]).toEqual({ type: 'start', scope: 'paper', id: 'p1', model_id: 'm1' })
  expect(result.current.on).toBe(true)
  expect(result.current.state).toBe('listening')
})

it('drives state from thinking to speaking to listening, sending one metrics and one finished', async () => {
  const { result, socket } = await started()
  ask(socket)
  expect(result.current.state).toBe('thinking')
  expect(socket.utterances).toHaveLength(1)
  sentence(socket)
  expect(result.current.state).toBe('speaking')
  expect(mocks.playback.play.mock.calls[0][1]).toBe(24000)
  sentence(socket, 1, 'More.')
  // speech ended at 10000 - 800 = 9200; heard at 10900 plus 20 ms of output delay
  expect(socket.json.filter((m) => m.type === 'metrics')).toEqual([
    { type: 'metrics', turn: 1, wait_ms: 800, output_ms: 20, total_ms: 10900 + 20 - 9200 },
  ])
  expect(mocks.playback.play.mock.calls[1][2]).toBeUndefined()
  mocks.playback.active.mockReturnValue(true)
  socket.say({ type: 'done' })
  expect(socket.json.some((m) => m.type === 'finished')).toBe(false) // still playing
  mocks.playback.active.mockReturnValue(false)
  act(() => mocks.onIdle?.())
  expect(socket.json.filter((m) => m.type === 'finished')).toHaveLength(1)
  expect(result.current.state).toBe('listening')
  expect(result.current.stream.status).toBe('done')
  expect(result.current.stream.question).toBe('What is it?')
  expect(result.current.stream.segments).toEqual([{ kind: 'text', text: 'It is a thing.More.' }])
})

it('sends finished at once when done arrives after playback already ended', async () => {
  const { socket } = await started()
  ask(socket)
  sentence(socket)
  socket.say({ type: 'done' })
  expect(socket.json.filter((m) => m.type === 'finished')).toHaveLength(1)
})

it('treats a turn that heard nothing as listening again', async () => {
  const { result, socket } = await started()
  act(() => handlers.onSpeechEnd(new Float32Array(16000)))
  socket.say({ type: 'turn', id: 'x', n: 1 })
  socket.say({ type: 'done' })
  expect(result.current.state).toBe('listening')
  expect(result.current.stream.status).toBe('idle')
  expect(socket.json.some((m) => m.type === 'finished')).toBe(false)
})

it('stops playback and reports what was heard when the reader talks over the answer', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  mocks.playback.playedSeconds.mockReturnValue(1.5)
  act(() => {
    for (let i = 0; i < 8; i++, now += 32) handlers.onFrame(0.9)
  })
  expect(mocks.playback.stop).toHaveBeenCalled()
  // the eighth voiced frame is 224 ms after the first; 20 ms of output delay on top
  expect(socket.json.find((m) => m.type === 'interrupt')).toEqual({ type: 'interrupt', played_seconds: 1.5, stop_ms: 224 + 20 })
  expect(result.current.state).toBe('listening')
})

it('does not send speech that began over the answer and never interrupted it', async () => {
  const { socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  act(() => handlers.onSpeechStart())
  mocks.playback.active.mockReturnValue(false) // the answer ended while that "speech" was still going
  act(() => handlers.onSpeechEnd(new Float32Array(16000)))
  expect(socket.utterances).toHaveLength(1) // only the real question
})

it('sends a question that was spoken while nothing played, after an interruption too', async () => {
  const { socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  act(() => handlers.onSpeechStart())
  act(() => {
    for (let i = 0; i < 8; i++, now += 32) handlers.onFrame(0.9)
  })
  mocks.playback.active.mockReturnValue(false)
  act(() => handlers.onSpeechEnd(new Float32Array(16000)))
  expect(socket.utterances).toHaveLength(2)
})

it('drops tokens, sentences and audio after an interruption until the next turn', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  act(() => {
    for (let i = 0; i < 8; i++, now += 32) handlers.onFrame(0.9)
  })
  const played = mocks.playback.play.mock.calls.length
  const segments = result.current.stream.segments
  sentence(socket, 1, 'Late.')
  expect(mocks.playback.play.mock.calls.length).toBe(played)
  expect(result.current.stream.segments).toBe(segments)
  socket.say({ type: 'turn', id: 'y', n: 2 })
  socket.say({ type: 'transcript', text: 'And?' })
  sentence(socket, 0, 'Next.')
  expect(mocks.playback.play.mock.calls.length).toBe(played + 1)
})

it('pairs audio with the latest sentence even when other messages come between, and tolerates a missing one', async () => {
  const { socket } = await started()
  ask(socket)
  socket.audio() // audio with no sentence before it: nothing to play it as
  expect(mocks.playback.play).not.toHaveBeenCalled()
  socket.say({ type: 'sentence', seq: 0, text: 'One.', rate: 22050 }) // cancelled: its audio never comes
  socket.say({ type: 'sentence', seq: 1, text: 'Two.', rate: 24000 })
  socket.say({ type: 'saved', output_id: 'o0' })
  socket.audio()
  expect(mocks.playback.play).toHaveBeenCalledOnce()
  expect(mocks.playback.play.mock.calls[0][1]).toBe(24000)
})

it('refreshes the history and keeps the saved id when an answer is saved', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  socket.say({ type: 'done' })
  socket.say({ type: 'saved', output_id: 'o1' })
  expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['papers', 'p1', 'chat'] })
  expect(result.current.stream.done?.output_id).toBe('o1')
})

it('threads a paper follow-up under the answer saved before it', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  socket.say({ type: 'done' })
  socket.say({ type: 'saved', output_id: 'o1' })
  ask(socket, 2)
  expect(result.current.stream.parentId).toBe('o1')
})

it('turns interruption off and says to use headphones when echo cancelling is not active', async () => {
  mocks.startMicrophone.mockImplementation(async (h: MicrophoneHandlers) => {
    handlers = h
    return { stop: mocks.micStop, echoCancelled: false }
  })
  const { result, socket } = await started()
  expect(result.current.problem).toBe(HEADPHONES)
  expect(result.current.state).toBe('listening')
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  act(() => {
    for (let i = 0; i < 20; i++, now += 32) handlers.onFrame(0.99)
  })
  expect(socket.json.some((m) => m.type === 'interrupt')).toBe(false)
  socket.say({ type: 'turn', id: 'z', n: 2 })
  expect(result.current.problem).toBe(HEADPHONES) // a new turn does not hide it
})

it('stops everything and says so when the socket closes mid-answer', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  act(() => socket.onclose?.())
  expect(mocks.playback.stop).toHaveBeenCalled()
  expect(mocks.micStop).toHaveBeenCalled()
  expect(result.current.problem).toBe(DROPPED)
  expect(result.current.on).toBe(false)
  expect(result.current.state).toBe('off')
})

it('stops the microphone, playback and socket when unmounted', async () => {
  const { unmount, socket } = await started()
  unmount()
  expect(mocks.micStop).toHaveBeenCalled()
  expect(mocks.playback.stop).toHaveBeenCalled()
  expect(socket.closed).toBe(true)
})

it('stop turns the microphone off without calling it a dropped connection', async () => {
  const { result, socket } = await started()
  await act(async () => result.current.stop())
  expect(result.current.state).toBe('off')
  expect(result.current.problem).toBeNull()
  expect(socket.closed).toBe(true)
  act(() => socket.onclose?.()) // the close it asked for
  expect(result.current.problem).toBeNull()
})

it('shows a model or speech error and keeps listening', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  socket.say({ type: 'error', message: 'The model stopped answering.', retryable: true })
  expect(result.current.problem).toBe('The model stopped answering.')
  expect(result.current.state).toBe('listening')
  expect(mocks.playback.stop).toHaveBeenCalled()
  expect(result.current.on).toBe(true)
})

it('shows why the microphone did not start and leaves nothing open', async () => {
  const { MicrophoneError } = await vi.importActual<typeof import('./microphone')>('./microphone')
  mocks.startMicrophone.mockRejectedValueOnce(new MicrophoneError('No microphone was found.'))
  const { result, socket } = await started()
  expect(result.current.problem).toBe('No microphone was found.')
  expect(result.current.on).toBe(false)
  expect(socket.closed).toBe(true)
})

it('shows the voice status detail and opens nothing when the voice program is down', async () => {
  vi.spyOn(api, 'voiceStatus').mockResolvedValue({ ready: false, detail: 'Start it with: make voice' })
  const { result } = await started()
  expect(result.current.problem).toBe('Start it with: make voice')
  expect(result.current.on).toBe(false)
  expect(FakeSocket.count).toBe(0)
  expect(mocks.startMicrophone).not.toHaveBeenCalled()
})

it('does not send an utterance over the API limit, and keeps listening', async () => {
  const { result, socket } = await started()
  act(() => handlers.onSpeechEnd(new Float32Array(16000 * 60 + 1)))
  expect(socket.utterances).toHaveLength(0)
  expect(result.current.problem).toBe('That was too long to send. Try a shorter question.')
  expect(result.current.state).toBe('listening')
})

const ENDED = 'The microphone stopped. Press the microphone to try again.'
const MUTED = "The microphone isn't sending any sound. Check your system settings."
const busy = (status: string) => status === 'sources' || status === 'streaming'

it('clears a half-asked or half-streamed answer when the microphone is turned off', async () => {
  const { result, socket } = await started()
  ask(socket)
  socket.say({ type: 'token', text: 'It is' })
  expect(busy(result.current.stream.status)).toBe(true)
  await act(async () => result.current.stop())
  expect(result.current.stream.status).toBe('idle')
})

it('moves a streaming answer to a stopped state when it is interrupted before done', async () => {
  const { result, socket } = await started()
  ask(socket)
  socket.say({ type: 'token', text: 'It is' })
  mocks.playback.active.mockReturnValue(true)
  mocks.playback.playedSeconds.mockReturnValue(0.5)
  act(() => {
    for (let i = 0; i < 8; i++, now += 32) handlers.onFrame(0.9)
  })
  expect(busy(result.current.stream.status)).toBe(false)
  expect(result.current.stream.segments).toEqual([{ kind: 'text', text: 'It is' }]) // what was shown stays
})

it('sends what was heard before closing when the microphone is turned off during playback', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  mocks.playback.playedSeconds.mockReturnValue(2.5)
  await act(async () => result.current.stop())
  expect(socket.json.filter((m) => m.type === 'interrupt')).toEqual([{ type: 'interrupt', played_seconds: 2.5, stop_ms: null }])
  expect(mocks.playback.stop).toHaveBeenCalled()
  expect(mocks.micStop).toHaveBeenCalled()
  expect(socket.closed).toBe(true)
})

it('sends no interrupt when the microphone is turned off while nothing plays', async () => {
  const { result, socket } = await started()
  await act(async () => result.current.stop())
  expect(socket.json.some((m) => m.type === 'interrupt')).toBe(false)
})

it('refreshes the history a moment after turning off mid-answer, since the socket is gone before the save', async () => {
  const { result, socket } = await started()
  ask(socket)
  sentence(socket)
  mocks.playback.active.mockReturnValue(true)
  vi.useFakeTimers({ toFake: ['setTimeout'] })
  try {
    await act(async () => result.current.stop())
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1000))
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['papers', 'p1', 'chat'] })
  } finally {
    vi.useRealTimers()
  }
})

it('stops voice and says so when the microphone track ends', async () => {
  const { result } = await started()
  act(() => handlers.onEnded())
  expect(result.current.problem).toBe(ENDED)
  expect(result.current.state).toBe('off')
  expect(mocks.micStop).toHaveBeenCalled()
  expect(FakeSocket.last.closed).toBe(true)
})

it('shows a muted microphone as a problem and clears it when sound returns', async () => {
  const { result } = await started()
  act(() => handlers.onMuted())
  expect(result.current.problem).toBe(MUTED)
  expect(result.current.state).toBe('listening')
  act(() => handlers.onUnmuted())
  expect(result.current.problem).toBeNull()
})

it('lets go of everything once when it is closed while the microphone is still starting', async () => {
  let opened!: () => void
  mocks.startMicrophone.mockImplementationOnce(
    (h: MicrophoneHandlers) =>
      new Promise((resolve) => {
        handlers = h
        opened = () => resolve({ stop: mocks.micStop, echoCancelled: true })
      }),
  )
  const hook = renderHook(() => useVoiceTurn(scope, null), { wrapper })
  act(() => void hook.result.current.start())
  await vi.waitFor(() => expect(mocks.startMicrophone).toHaveBeenCalled())
  const ctx = FakeContext.last
  ctx.close.mockRejectedValue(new Error('already closed'))
  hook.unmount()
  opened()
  await vi.waitFor(() => expect(mocks.micStop).toHaveBeenCalled())
  expect(mocks.micStop).toHaveBeenCalledTimes(1)
  expect(ctx.close).toHaveBeenCalledTimes(1)
})

it('stops voice when the chat moves to another scope', async () => {
  const hook = renderHook(({ target }) => useVoiceTurn(target, null), {
    wrapper,
    initialProps: { target: { kind: 'paper', id: 'a' } as ChatScope },
  })
  await act(async () => {
    await hook.result.current.start()
  })
  const socket = FakeSocket.last
  expect(hook.result.current.on).toBe(true)
  hook.rerender({ target: { kind: 'paper', id: 'b' } })
  expect(mocks.micStop).toHaveBeenCalled()
  expect(socket.closed).toBe(true)
  expect(hook.result.current.on).toBe(false)
  expect(hook.result.current.stream.status).toBe('idle')
})

const moveTo = (hook: { rerender: (props: { target: ChatScope }) => void }) =>
  hook.rerender({ target: { kind: 'paper', id: 'b' } })
const onPaperA = () =>
  renderHook(({ target }) => useVoiceTurn(target, null), {
    wrapper,
    initialProps: { target: { kind: 'paper', id: 'a' } as ChatScope },
  })

it('changing scope while the voice status is being checked opens nothing', async () => {
  let ready!: () => void
  vi.spyOn(api, 'voiceStatus').mockImplementation(() => new Promise((resolve) => (ready = () => resolve({ ready: true, detail: null }))))
  const hook = onPaperA()
  act(() => void hook.result.current.start())
  moveTo(hook)
  await act(async () => ready())
  expect(FakeSocket.count).toBe(0)
  expect(mocks.startMicrophone).not.toHaveBeenCalled()
  expect(FakeContext.last.close).toHaveBeenCalledTimes(1)
  expect(hook.result.current.on).toBe(false)
  expect(hook.result.current.problem).toBeNull()
})

it('changing scope while the socket is opening never opens a session on the old paper', async () => {
  FakeSocket.hold = true
  const hook = onPaperA()
  act(() => void hook.result.current.start())
  await vi.waitFor(() => expect(FakeSocket.count).toBe(1))
  const socket = FakeSocket.last
  moveTo(hook)
  await act(async () => socket.onopen?.())
  expect(socket.json).toEqual([]) // no start message for paper a
  expect(socket.closed).toBe(true)
  expect(mocks.startMicrophone).not.toHaveBeenCalled()
  expect(FakeContext.last.close).toHaveBeenCalledTimes(1)
  expect(hook.result.current.on).toBe(false)
  expect(hook.result.current.problem).toBeNull()
})

it('changing scope while the microphone is starting releases the mic', async () => {
  let opened!: () => void
  mocks.startMicrophone.mockImplementationOnce(
    () => new Promise((resolve) => (opened = () => resolve({ stop: mocks.micStop, echoCancelled: true }))),
  )
  const hook = onPaperA()
  act(() => void hook.result.current.start())
  await vi.waitFor(() => expect(mocks.startMicrophone).toHaveBeenCalled())
  const socket = FakeSocket.last
  moveTo(hook)
  await act(async () => opened())
  expect(mocks.micStop).toHaveBeenCalledTimes(1)
  expect(socket.closed).toBe(true)
  expect(hook.result.current.on).toBe(false)
  expect(hook.result.current.problem).toBeNull()
})
