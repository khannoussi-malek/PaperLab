import { useEffect, useRef, useState } from 'react'
import { api, type ChatScope, type ChatSourcesEvent } from '@/api/client'
import { useInvalidateChatHistory } from '@/api/queries'
import { appendSegments, citationSplitter } from '../chat/citations'
import { IDLE, type ChatStream } from '../chat/useChatStream'
import { FRAME_MS, INTERRUPT_SUSTAIN_MS, INTERRUPT_THRESHOLD, MAX_UTTERANCE_BYTES, SILENCE_MS } from './constants'
import { createInterruptDetector } from './interruptDetector'
import { startMicrophone, type Microphone } from './microphone'
import { createPlayback, type Playback } from './playback'

export type VoiceState = 'off' | 'listening' | 'thinking' | 'speaking'

const HEADPHONES = 'Use headphones to talk over answers. Without echo cancelling, the app would hear itself.'
const DROPPED = 'The voice connection dropped. Press the microphone to try again.'
const TOO_LONG = 'That was too long to send. Try a shorter question.'
const ENDED = 'The microphone stopped. Press the microphone to try again.'
const MUTED = "The microphone isn't sending any sound. Check your system settings."
// Turning off mid-answer closes the socket before the server has saved what was heard; look again after it has.
const SAVE_REFRESH_MS = 1000

/** What the server sends (backend/app/api/voice.py); audio arrives as binary frames between them. */
type ServerMessage =
  | { type: 'turn'; id: string; n: number }
  | { type: 'transcript'; text: string }
  | ({ type: 'sources' } & ChatSourcesEvent)
  | { type: 'token'; text: string }
  | { type: 'sentence'; seq: number; text: string; rate: number }
  | { type: 'done' }
  | { type: 'error'; message: string; retryable: boolean }
  | { type: 'saved'; output_id: string }

/** Everything that lives while the microphone is on. Mutated by the socket and microphone events. */
type Session = {
  ctx: AudioContext
  socket: WebSocket
  playback: Playback
  detector: ReturnType<typeof createInterruptDetector>
  mic: Microphone | null
  closing: boolean // we asked for the close
  talkOver: boolean // false without echo cancelling: the app would interrupt itself
  notice: string | null // a problem that stays for the whole session
  lastSaved: string | null // the answer a paper follow-up continues
  speechOverAnswer: boolean // the speech now under way began while an answer played
  barged: boolean // ... and it interrupted that answer
  // The turn under way. Frames carry no turn id: `accepting` is false from an interrupt until the next `turn`.
  accepting: boolean
  turn: number
  heard: boolean
  speechEnd: number
  sentenceRate: number | null
  splitter: ReturnType<typeof citationSplitter>
  audioQueued: boolean
  done: boolean
  finished: boolean
}

const voiceUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/voice/ws`

function openSocket(first: object): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(voiceUrl())
    socket.binaryType = 'arraybuffer'
    socket.onopen = () => {
      socket.send(JSON.stringify(first))
      resolve(socket)
    }
    socket.onerror = () => reject(new Error(DROPPED))
  })
}

const send = (s: Session, message: object) => s.socket.send(JSON.stringify(message))

/** A live stream cut short keeps what it showed, as a stopped answer; one that showed nothing goes away. */
const cutShort = (stream: ChatStream): ChatStream =>
  stream.status !== 'sources' && stream.status !== 'streaming'
    ? stream
    : stream.segments.length > 0
      ? { ...stream, status: 'error' }
      : IDLE

/**
 * Asking out loud: the microphone, the local voice WebSocket and playback of the streamed answer. `stream` has typed
 * chat's shape, so the panel renders either. The connection is made for the `scope` and `modelId` at the moment the
 * microphone is turned on. ponytail: picking another model applies the next time the microphone is turned on.
 */
export function useVoiceTurn(scope: ChatScope, modelId: string | null) {
  const [state, setState] = useState<VoiceState>('off')
  const [stream, setStream] = useState<ChatStream>(IDLE)
  const [problem, setProblem] = useState<string | null>(null)
  const invalidateHistory = useInvalidateChatHistory(scope)
  const latest = useRef({ scope, modelId, invalidateHistory })
  const session = useRef<Session | null>(null)
  const starting = useRef(false)
  const mounted = useRef(false)
  useEffect(() => {
    latest.current = { scope, modelId, invalidateHistory }
  })

  /** Lets go of the microphone, playback and socket; safe to repeat. */
  function release(s: Session) {
    if (s.closing) return
    s.closing = true
    s.playback.stop()
    s.mic?.stop().catch((error: unknown) => console.warn('the microphone did not stop cleanly', error))
    s.socket.close()
    s.ctx.close().catch(() => {}) // already closed is the only way this fails
    if (session.current === s) session.current = null
  }

  /** Turning off: what was heard of an answer still playing is saved, then everything is released. */
  function stop() {
    const s = session.current
    if (s?.playback.active()) {
      send(s, { type: 'interrupt', played_seconds: s.playback.playedSeconds(), stop_ms: null })
      setTimeout(() => void latest.current.invalidateHistory(), SAVE_REFRESH_MS)
    }
    if (s) release(s)
    setState('off')
    setProblem(null)
    setStream(IDLE)
  }

  // Also when the chat moves to another paper or workspace: the session is bound to the one it started for.
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      stop()
    }
    // stop only reads refs and calls state setters
  }, [scope.kind, scope.id])

  function finishIfIdle(s: Session) {
    if (!s.done || s.finished || s.playback.active()) return
    s.finished = true
    send(s, { type: 'finished' })
    setState('listening')
  }

  function reportFirstHeard(s: Session, playedAt: number) {
    const outputMs = Math.round(s.ctx.outputLatency * 1000)
    const totalMs = Math.max(0, Math.round(playedAt + outputMs - s.speechEnd))
    send(s, { type: 'metrics', turn: s.turn, wait_ms: SILENCE_MS, output_ms: outputMs, total_ms: totalMs })
  }

  function interrupt(s: Session, startedAt: number) {
    const playedSeconds = s.playback.playedSeconds()
    const stopMs = Math.round(performance.now() - startedAt + s.ctx.outputLatency * 1000)
    s.playback.stop()
    s.accepting = false
    s.barged = true
    send(s, { type: 'interrupt', played_seconds: playedSeconds, stop_ms: stopMs })
    setState('listening')
    setStream(playedSeconds === 0 ? IDLE : cutShort) // nothing heard, nothing saved; else what showed stays, stopped
  }

  function sendUtterance(s: Session, audio: Float32Array) {
    // Speech that began over the answer and never interrupted it was the app's own voice.
    if (s.playback.active() || (s.speechOverAnswer && !s.barged)) return
    if (audio.byteLength > MAX_UTTERANCE_BYTES) return setProblem(TOO_LONG)
    s.speechEnd = performance.now() - SILENCE_MS
    s.socket.send(audio.slice().buffer)
    setState('thinking')
  }

  function onAudio(s: Session, samples: Float32Array) {
    const rate = s.sentenceRate
    s.sentenceRate = null // its sentence may be missing (a cancelled turn): then there is nothing to play it as
    if (!s.accepting || rate === null) return
    const first = !s.audioQueued
    s.audioQueued = true
    s.playback.play(samples, rate, first ? (playedAt) => reportFirstHeard(s, playedAt) : undefined)
    setState('speaking')
  }

  function startTurn(s: Session, number: number) {
    const fresh = { accepting: true, turn: number, heard: false, audioQueued: false, done: false, finished: false }
    Object.assign(s, fresh, { sentenceRate: null })
    s.splitter = citationSplitter(new Set())
    s.playback.stop()
    setStream(IDLE)
    setProblem(s.notice)
  }

  function onSaved(s: Session, outputId: string) {
    s.lastSaved = outputId
    const done = { output_id: outputId, model: '', connection_name: '', prompt_version: 0, cited: [] }
    setStream((prev) => (prev.status === 'idle' ? prev : { ...prev, done }))
    void latest.current.invalidateHistory()
  }

  function onError(s: Session, message: string) {
    s.accepting = false
    s.playback.stop()
    setProblem(message)
    setState('listening')
    setStream(cutShort)
  }

  function onMessage(s: Session, m: ServerMessage) {
    if (m.type === 'turn') return startTurn(s, m.n)
    if (m.type === 'saved') return onSaved(s, m.output_id)
    if (m.type === 'error') return onError(s, m.message)
    if (!s.accepting) return // after an interrupt: the rest of that turn's tokens and sentences
    if (m.type === 'transcript') {
      s.heard = true
      const parentId = latest.current.scope.kind === 'paper' ? s.lastSaved : null
      setStream({ ...IDLE, status: 'sources', question: m.text, parentId })
    } else if (m.type === 'sources') {
      s.splitter = citationSplitter(new Set([...m.sources, ...m.notes].map((source) => source.label)))
      const { sources, whole_paper: wholePaper, notes, notes_used: notesUsed, notes_total: notesTotal } = m
      setStream((prev) => ({ ...prev, sources, wholePaper, notes, notesUsed, notesTotal }))
    } else if (m.type === 'token') {
      const added = s.splitter.feed(m.text)
      setStream((prev) => ({ ...prev, status: 'streaming', segments: appendSegments(prev.segments, added) }))
    } else if (m.type === 'sentence') {
      s.sentenceRate = m.rate
    } else if (m.type === 'done') {
      s.done = true
      if (!s.heard) return setState('listening') // noise that transcribed to nothing: no question, no answer
      const tail = s.splitter.flush()
      setStream((prev) => ({ ...prev, status: 'done', segments: appendSegments(prev.segments, tail) }))
      finishIfIdle(s)
    }
  }

  function dropped(s: Session) {
    if (s.closing) return
    release(s)
    setStream(cutShort)
    setProblem(DROPPED)
    setState('off')
  }

  function open(ctx: AudioContext, socket: WebSocket): Session {
    const s: Session = {
      ctx,
      socket,
      playback: createPlayback(ctx, ctx.destination, () => finishIfIdle(s)),
      detector: createInterruptDetector({
        threshold: INTERRUPT_THRESHOLD,
        sustainMs: INTERRUPT_SUSTAIN_MS,
        frameMs: FRAME_MS,
        onTrigger: (startedAt) => interrupt(s, startedAt),
      }),
      mic: null,
      closing: false,
      talkOver: true,
      notice: null,
      lastSaved: null,
      speechOverAnswer: false,
      barged: false,
      accepting: false,
      turn: 0,
      heard: false,
      speechEnd: 0,
      sentenceRate: null,
      splitter: citationSplitter(new Set()),
      audioQueued: false,
      done: false,
      finished: false,
    }
    socket.onmessage = ({ data }) => {
      if (typeof data !== 'string') return onAudio(s, new Float32Array(data as ArrayBuffer))
      try {
        onMessage(s, JSON.parse(data) as ServerMessage)
      } catch (error) {
        console.warn('a voice message could not be read', error)
      }
    }
    socket.onclose = () => dropped(s)
    return s
  }

  /** Turns the microphone on. Call it from the click, so the browser lets the answer play. */
  async function start() {
    if (session.current || starting.current) return
    starting.current = true
    setProblem(null)
    const ctx = new AudioContext()
    void ctx.resume()
    let socket: WebSocket | undefined
    try {
      const status = await api.voiceStatus()
      if (!status.ready) throw new Error(status.detail ?? 'The voice program is not ready.')
      const { scope: target, modelId: model } = latest.current
      socket = await openSocket({ type: 'start', scope: target.kind, id: target.id, model_id: model })
      const s = open(ctx, socket)
      session.current = s
      const mic = await startMicrophone({
        onFrame: (probability) => s.detector.frame(probability, s.talkOver && s.playback.active(), performance.now()),
        onSpeechStart: () => {
          s.speechOverAnswer = s.playback.active()
          s.barged = false
        },
        onSpeechEnd: (audio) => sendUtterance(s, audio),
        onEnded: () => {
          if (session.current !== s) return
          stop()
          setProblem(ENDED)
        },
        onMuted: () => setProblem(MUTED),
        onUnmuted: () => setProblem(s.notice),
      })
      s.mic = mic
      if (s.closing) return void mic.stop().catch(() => {}) // closed while the microphone was starting
      if (!mounted.current) return release(s)
      if (!mic.echoCancelled) {
        s.talkOver = false
        s.notice = HEADPHONES
        setProblem(HEADPHONES)
      }
      setState('listening')
    } catch (error) {
      if (session.current) release(session.current)
      else {
        socket?.close()
        ctx.close().catch(() => {})
      }
      setProblem(error instanceof Error ? error.message : DROPPED)
      setState('off')
    } finally {
      starting.current = false
    }
  }

  return { on: state !== 'off', state, stream, problem, start, stop }
}
