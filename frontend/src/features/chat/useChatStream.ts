import { useState } from 'react'
import {
  api,
  errorDetail,
  type ChatDoneEvent,
  type ChatErrorEvent,
  type ChatSource,
  type ChatSourcesEvent,
  type ChatTokenEvent,
} from '@/api/client'
import { useInvalidateChatHistory } from '@/api/queries'
import { appendSegments, citationSplitter, type Segment } from './citations'
import { readSse } from './sse'

export type ChatProblem = { message: string; retryable: boolean; reindex: boolean }

/** `sources`: asked, nothing streamed yet. `sources` stays null until its event arrives. */
export type ChatStream = {
  status: 'idle' | 'sources' | 'streaming' | 'done' | 'error'
  question: string
  sources: ChatSource[] | null
  wholePaper: boolean
  segments: Segment[]
  done: ChatDoneEvent | null
  problem: ChatProblem | null
}

const IDLE: ChatStream = {
  status: 'idle',
  question: '',
  sources: null,
  wholePaper: false,
  segments: [],
  done: null,
  problem: null,
}

// The 409s POST /chat answers before streaming (spec §3.10), in words. Any other refusal shows its detail.
const REFUSALS: Record<string, ChatProblem> = {
  paper_not_ready: {
    message: 'This paper is still being processed. Ask again once it is ready.',
    retryable: true,
    reindex: false,
  },
  paper_not_indexed: {
    message: 'This paper was added before chat existed, so it has no search index yet.',
    retryable: false,
    reindex: true,
  },
}

const STOPPED: ChatProblem = { message: 'The answer stopped before it finished.', retryable: true, reindex: false }

/** Asks one question and follows its SSE stream: idle → sources → streaming → done | error. */
export function useChatStream(paperId: string) {
  const [stream, setStream] = useState<ChatStream>(IDLE)
  const invalidateHistory = useInvalidateChatHistory(paperId)

  async function ask(question: string) {
    setStream({ ...IDLE, status: 'sources', question })
    const fail = (problem: ChatProblem, tail: Segment[] = []) =>
      setStream((s) => ({ ...s, status: 'error', problem, segments: appendSegments(s.segments, tail) }))

    const response = await api.askChat(paperId, question).catch(() => null)
    if (!response) return fail({ message: "Can't reach the PaperLab API.", retryable: true, reindex: false })
    if (!response.ok || !response.body) {
      const detail = await errorDetail(response)
      return fail(REFUSALS[detail] ?? { message: detail, retryable: false, reindex: false })
    }

    let splitter = citationSplitter(new Set())
    try {
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'sources') {
          const { sources, whole_paper } = JSON.parse(data) as ChatSourcesEvent
          splitter = citationSplitter(new Set(sources.map((source) => source.label)))
          setStream((s) => ({ ...s, sources, wholePaper: whole_paper }))
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
