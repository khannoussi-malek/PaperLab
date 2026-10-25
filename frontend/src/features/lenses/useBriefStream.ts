import { useEffect, useRef, useState } from 'react'
import {
  api,
  errorDetail,
  type ChatDoneEvent,
  type ChatErrorEvent,
  type ChatSource,
  type ChatSourcesEvent,
  type ChatTokenEvent,
  type LensId,
} from '@/api/client'
import { useInvalidateBriefs } from './queries'
import { appendSegments, citationSplitter, type Segment } from '@/features/chat/citations'
import type { ChatProblem } from '@/features/chat/refusals'
import { readSse } from '@/features/chat/sse'
import { briefProblem } from './lenses'

/** One brief being written: idle → sources → streaming → done | error, for `lens`. */
export type BriefStream = {
  status: 'idle' | 'sources' | 'streaming' | 'done' | 'error'
  lens: LensId | null
  sources: ChatSource[] | null
  segments: Segment[]
  /** The saved brief's id, once `done`. */
  outputId: string | null
  problem: ChatProblem | null
}

const IDLE: BriefStream = { status: 'idle', lens: null, sources: null, segments: [], outputId: null, problem: null }
const UNREACHABLE: ChatProblem = { message: "Can't reach the PaperLab API.", retryable: true, reindex: false }
const STOPPED: ChatProblem = { message: 'The brief stopped before it finished.', retryable: true, reindex: false }

/**
 * Writes one brief with the default model and follows its SSE stream (chat's events). Unmounting stops updating the
 * card but lets the brief finish; the server saves it. A new brief cancels the one before it.
 */
export function useBriefStream(paperId: string) {
  const [stream, setStream] = useState<BriefStream>(IDLE)
  const invalidateBriefs = useInvalidateBriefs(paperId)
  const controller = useRef<AbortController | null>(null)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  async function generate(lens: LensId, lensLabel: string) {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    const set = (update: (s: BriefStream) => BriefStream) => mounted.current && !current.signal.aborted && setStream(update)
    const fail = (problem: ChatProblem, tail: Segment[] = []) =>
      set((s) => ({ ...s, status: 'error', problem, segments: appendSegments(s.segments, tail) }))

    set(() => ({ ...IDLE, status: 'sources', lens }))
    const response = await api.generateBrief(paperId, lens, null, current.signal).catch(() => null)
    if (!response) return fail(UNREACHABLE)
    if (!response.ok || !response.body) return fail(briefProblem(response.status, await errorDetail(response), lensLabel))

    let splitter = citationSplitter(new Set())
    try {
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'sources') {
          const { sources } = JSON.parse(data) as ChatSourcesEvent
          splitter = citationSplitter(new Set(sources.map((source) => source.label)))
          set((s) => ({ ...s, sources }))
        } else if (event === 'token') {
          const added = splitter.feed((JSON.parse(data) as ChatTokenEvent).text)
          set((s) => ({ ...s, status: 'streaming', segments: appendSegments(s.segments, added) }))
        } else if (event === 'done') {
          const { output_id } = JSON.parse(data) as ChatDoneEvent
          const tail = splitter.flush()
          set((s) => ({ ...s, status: 'done', outputId: output_id, segments: appendSegments(s.segments, tail) }))
          return void invalidateBriefs()
        } else if (event === 'error') {
          const { message, retryable } = JSON.parse(data) as ChatErrorEvent
          return fail({ message, retryable, reindex: false }, splitter.flush())
        }
      }
    } catch (error) {
      // A dropped connection or a malformed event: the same as a stream that ends without `done`.
      if (!current.signal.aborted) console.warn('brief stream ended early', error)
    }
    fail(STOPPED, splitter.flush())
  }

  return { stream, generate }
}
