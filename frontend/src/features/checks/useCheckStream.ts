import { useEffect, useRef, useState } from 'react'
import { api, errorDetail, type ChatErrorEvent, type ChatSource, type ChatSourcesEvent, type ChatTokenEvent, type NoteKind } from '@/api/client'
import { useChatModels } from '@/api/queries'
import { loadChatModel } from '@/features/chat/chatModel'
import type { ChatProblem } from '@/features/chat/refusals'
import { readSse } from '@/features/chat/sse'
import { browserStorage } from '@/features/notes/highlightColors'
import { checkProblem, streamedLine, type CheckLine } from './exitTest'
import { useInvalidateChecks } from './queries'

/** One check being run: idle → (confirm →) sources → streaming → done | error. `host`: where a remote model would send the note. */
export type CheckStream = {
  status: 'idle' | 'confirm' | 'sources' | 'streaming' | 'done' | 'error'
  host: string | null
  sources: ChatSource[] | null
  lines: CheckLine[]
  problem: ChatProblem | null
}

const IDLE: CheckStream = { status: 'idle', host: null, sources: null, lines: [], problem: null }
const UNREACHABLE: ChatProblem = { message: "Can't reach the PaperLab API.", retryable: true, reindex: false }
const STOPPED: ChatProblem = { message: 'The check stopped before it finished.', retryable: true, reindex: false }

/**
 * Checks one note with the remembered chat model and follows its SSE stream. A token is one line the server kept, so
 * no model text is parsed here beyond `streamedLine`. A remote model first asks (`confirm`); `run(true)` sends.
 */
export function useCheckStream(noteId: string, paperId: string, kind: NoteKind = 'summary') {
  const [stream, setStream] = useState<CheckStream>(IDLE)
  const invalidateChecks = useInvalidateChecks(paperId)
  const models = useChatModels().data ?? []
  const controller = useRef<AbortController | null>(null)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  async function run(confirmRemote = false) {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    const set = (update: (s: CheckStream) => CheckStream) => mounted.current && !current.signal.aborted && setStream(update)
    const fail = (problem: ChatProblem) => set((s) => ({ ...s, status: 'error', problem }))

    set(() => ({ ...IDLE, status: 'sources' }))
    const modelId = loadChatModel(browserStorage(), models)
    const response = await api.checkNote(noteId, modelId, confirmRemote, current.signal).catch(() => null)
    if (!response) return fail(UNREACHABLE)
    if (!response.ok || !response.body) {
      const detail = await errorDetail(response.clone())
      if (response.status === 409 && detail === 'remote_model_needs_confirm') {
        const body: { host?: unknown } = await response.clone().json().catch(() => ({}))
        return set(() => ({ ...IDLE, status: 'confirm', host: typeof body.host === 'string' ? body.host : 'a remote model' }))
      }
      return fail(checkProblem(response.status, detail, kind))
    }

    try {
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'sources') {
          const { sources } = JSON.parse(data) as ChatSourcesEvent
          set((s) => ({ ...s, sources }))
        } else if (event === 'token') {
          const line = streamedLine((JSON.parse(data) as ChatTokenEvent).text)
          if (line) set((s) => ({ ...s, status: 'streaming', lines: [...s.lines, line] }))
        } else if (event === 'done') {
          set((s) => ({ ...s, status: 'done' }))
          return void invalidateChecks()
        } else if (event === 'error') {
          const { message, retryable } = JSON.parse(data) as ChatErrorEvent
          return fail({ message, retryable, reindex: false })
        }
      }
    } catch (error) {
      // A dropped connection or a malformed event: the same as a stream that ends without `done`.
      if (!current.signal.aborted) console.warn('check stream ended early', error)
    }
    fail(STOPPED)
  }

  const cancelConfirm = () => setStream(IDLE)

  return { stream, run, cancelConfirm }
}
