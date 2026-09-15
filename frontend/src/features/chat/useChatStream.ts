import { useEffect, useRef, useState } from 'react'
import {
  api,
  errorDetail,
  type ChatDoneEvent,
  type ChatErrorEvent,
  type ChatScope,
  type ChatSource,
  type ChatSourcesEvent,
  type ChatTokenEvent,
  type NoteSource,
} from '@/api/client'
import { useInvalidateChatHistory, useInvalidateModels } from '@/api/queries'
import { appendSegments, citationSplitter, type Segment } from './citations'
import { refusal, type ChatProblem } from './refusals'
import { readSse } from './sse'

/** `sources`: asked, nothing streamed yet. `sources` stays null until its event arrives. */
export type ChatStream = {
  status: 'idle' | 'sources' | 'streaming' | 'done' | 'error'
  question: string
  sources: ChatSource[] | null
  wholePaper: boolean
  /** Workspace chat only: the notes the answer can cite, and how many of the workspace's notes fit the prompt. */
  notes: NoteSource[]
  notesUsed: number | null
  notesTotal: number | null
  segments: Segment[]
  done: ChatDoneEvent | null
  problem: ChatProblem | null
}

const IDLE: ChatStream = {
  status: 'idle',
  question: '',
  sources: null,
  wholePaper: false,
  notes: [],
  notesUsed: null,
  notesTotal: null,
  segments: [],
  done: null,
  problem: null,
}

const STOPPED: ChatProblem = { message: 'The answer stopped before it finished.', retryable: true, reindex: false }

/**
 * Asks one question with the model `modelId` (null: the default) and follows its SSE stream:
 * idle → sources → streaming → done | error. Unmounting stops updating the panel but lets the answer finish; the
 * server saves it. Asking again while one streams cancels the one before it.
 */
export function useChatStream(scope: ChatScope, modelId: string | null) {
  const [stream, setStream] = useState<ChatStream>(IDLE)
  const invalidateHistory = useInvalidateChatHistory(scope)
  const invalidateModels = useInvalidateModels()
  const controller = useRef<AbortController | null>(null)
  // Starts false, set true by the effect: React (StrictMode) mounts, cleans up and remounts every component once,
  // so only the effect body -- not the initial ref value -- sees the real, final mount.
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  async function ask(question: string) {
    controller.current?.abort() // a newer question replaces whatever this panel was still asking
    const current = new AbortController()
    controller.current = current
    // Also guards against a superseded question's events that were already parsed out of a chunk its reader had
    // buffered before the abort took effect: without the aborted check here, those still reach `setStream`, since
    // draining an async generator's already-yielded backlog doesn't itself touch the (now rejecting) reader again.
    const set = (updater: (s: ChatStream) => ChatStream) => mounted.current && !current.signal.aborted && setStream(updater)

    set(() => ({ ...IDLE, status: 'sources', question }))
    const fail = (problem: ChatProblem, tail: Segment[] = []) =>
      set((s) => ({ ...s, status: 'error', problem, segments: appendSegments(s.segments, tail) }))

    const response = await api.askChat(scope, question, modelId, current.signal).catch(() => null)
    if (!response) return fail({ message: "Can't reach the PaperLab API.", retryable: true, reindex: false })
    if (!response.ok || !response.body) {
      // A removed model or a missing default: the dropdown refetches and falls back.
      void invalidateModels()
      return fail(refusal(response.status, await errorDetail(response)))
    }

    let splitter = citationSplitter(new Set())
    try {
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'sources') {
          const { sources, whole_paper, notes, notes_used, notes_total } = JSON.parse(data) as ChatSourcesEvent
          splitter = citationSplitter(new Set([...sources, ...notes].map((source) => source.label)))
          set((s) => ({
            ...s,
            sources,
            wholePaper: whole_paper,
            notes,
            notesUsed: notes_used,
            notesTotal: notes_total,
          }))
        } else if (event === 'token') {
          const added = splitter.feed((JSON.parse(data) as ChatTokenEvent).text)
          set((s) => ({ ...s, status: 'streaming', segments: appendSegments(s.segments, added) }))
        } else if (event === 'done') {
          const done = JSON.parse(data) as ChatDoneEvent
          const tail = splitter.flush()
          set((s) => ({ ...s, status: 'done', done, segments: appendSegments(s.segments, tail) }))
          return void invalidateHistory()
        } else if (event === 'error') {
          const { message, retryable } = JSON.parse(data) as ChatErrorEvent
          return fail({ message, retryable, reindex: false }, splitter.flush())
        }
      }
    } catch (error) {
      // A dropped connection or a malformed event: same as a stream that ends without `done`.
      if (!current.signal.aborted) console.warn('chat stream ended early', error)
    }
    fail(STOPPED, splitter.flush())
  }

  return { stream, ask, retry: () => ask(stream.question) }
}
