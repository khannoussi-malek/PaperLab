import { useEffect, useRef, useState } from 'react'
import { api, errorDetail, type LLMModel, type PullDoneEvent, type PullErrorEvent, type PullProgressEvent } from '@/api/client'
import { useInvalidateModels } from '@/api/queries'
import { readSse } from '@/features/chat/sse'

export type PullState =
  | { status: 'idle' }
  | { status: 'pulling'; name: string; line: PullProgressEvent | null }
  | { status: 'done'; name: string }
  | { status: 'error'; name: string; message: string }

/**
 * Pulls a model on an Ollama connection and follows its progress events. Leaving the page aborts the request,
 * which stops the download itself, not just the following: coming back needs a new Pull. `onDone` runs once the
 * model is there, with the model chat now lists (the first-run setup makes it the default).
 */
export function usePullModel(connectionId: string, { onDone }: { onDone?: (model: LLMModel) => void } = {}) {
  const [state, setState] = useState<PullState>({ status: 'idle' })
  const invalidateModels = useInvalidateModels()
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  async function pull(name: string) {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setState({ status: 'pulling', name, line: null })
    const fail = (message: string) => setState({ status: 'error', name, message })
    try {
      const response = await api.pullModel(connectionId, name, current.signal)
      if (!response.ok || !response.body) return fail(await errorDetail(response))
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'progress') setState({ status: 'pulling', name, line: JSON.parse(data) as PullProgressEvent })
        if (event === 'error') return fail((JSON.parse(data) as PullErrorEvent).message)
        if (event === 'done') {
          const { model } = JSON.parse(data) as PullDoneEvent
          setState({ status: 'done', name: model.name })
          onDone?.(model)
          return void invalidateModels()
        }
      }
      fail('The download stopped before it finished.')
    } catch (error) {
      if (current.signal.aborted) return
      console.warn('model pull stream failed', error)
      fail("Can't reach the PaperLab API.")
    }
  }

  return { state, pull }
}
