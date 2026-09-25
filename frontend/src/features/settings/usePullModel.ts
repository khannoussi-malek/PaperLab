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
 * `addToChat` false: Settings → Search's pull (never listed in chat); `onDone` runs once the model is there.
 *
 * `onDone` keeps taking the pulled model (deviates from the plan's literal `() => void`; see task-9-report.md):
 * `addToChat` false never has one to pass (D152), but SetupChat.tsx's `onDone` sets the pulled model as chat's
 * default from its `id`, which only a real model carries — dropping the parameter entirely would have broken that
 * (and its Playwright coverage in e2e/first-run.spec.ts) for no gain, since a future zero-arg caller still satisfies
 * this type.
 */
export function usePullModel(
  connectionId: string,
  { addToChat = true, onDone }: { addToChat?: boolean; onDone?: (model: LLMModel) => void } = {},
) {
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
      const response = await api.pullModel(connectionId, name, current.signal, addToChat)
      if (!response.ok || !response.body) return fail(await errorDetail(response))
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'progress') setState({ status: 'pulling', name, line: JSON.parse(data) as PullProgressEvent })
        if (event === 'error') return fail((JSON.parse(data) as PullErrorEvent).message)
        if (event === 'done') {
          // A pull for search lists nothing in chat, so its done event carries no model (D152).
          const { model } = JSON.parse(data) as PullDoneEvent
          setState({ status: 'done', name: model?.name ?? name })
          if (model) onDone?.(model)
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
