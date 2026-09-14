import { useState } from 'react'
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
import { useInvalidateChatHistory } from '@/api/queries'
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

/** Asks one question and follows its SSE stream: idle → sources → streaming → done | error. */
export function useChatStream(scope: ChatScope) {
  const [stream, setStream] = useState<ChatStream>(IDLE)
  const invalidateHistory = useInvalidateChatHistory(scope)

  async function ask(question: string) {
    setStream({ ...IDLE, status: 'sources', question })
    const fail = (problem: ChatProblem, tail: Segment[] = []) =>
      setStream((s) => ({ ...s, status: 'error', problem, segments: appendSegments(s.segments, tail) }))

    const response = await api.askChat(scope, question).catch(() => null)
    if (!response) return fail({ message: "Can't reach the PaperLab API.", retryable: true, reindex: false })
    if (!response.ok || !response.body) return fail(refusal(response.status, await errorDetail(response)))

    let splitter = citationSplitter(new Set())
    try {
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'sources') {
          const { sources, whole_paper, notes, notes_used, notes_total } = JSON.parse(data) as ChatSourcesEvent
          splitter = citationSplitter(new Set([...sources, ...notes].map((source) => source.label)))
          setStream((s) => ({
            ...s,
            sources,
            wholePaper: whole_paper,
            notes,
            notesUsed: notes_used,
            notesTotal: notes_total,
          }))
        } else if (event === 'token') {
          const added = splitter.feed((JSON.parse(data) as ChatTokenEvent).text)
          setStream((s) => ({ ...s, status: 'streaming', segments: appendSegments(s.segments, added) }))
        } else if (event === 'done') {
          const done = JSON.parse(data) as ChatDoneEvent
          const tail = splitter.flush()
          setStream((s) => ({ ...s, status: 'done', done, segments: appendSegments(s.segments, tail) }))
          return void invalidateHistory()
        } else if (event === 'error') {
          const { message, retryable } = JSON.parse(data) as ChatErrorEvent
          return fail({ message, retryable, reindex: false }, splitter.flush())
        }
      }
    } catch {
      // A dropped connection or a malformed event: same as a stream that ends without `done`.
    }
    fail(STOPPED, splitter.flush())
  }

  return { stream, ask, retry: () => ask(stream.question) }
}
