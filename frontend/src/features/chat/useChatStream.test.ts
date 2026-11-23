// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { useChatStream } from './useChatStream'

vi.mock('@/api/queries', () => ({ useInvalidateChatHistory: () => vi.fn(), useInvalidateModels: () => vi.fn() }))

const sse = (...events: [string, unknown][]) =>
  new Response(events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(''), {
    headers: { 'content-type': 'text/event-stream' },
  })
const reading = (label: string, done: number) => ({
  paper_id: label, label, status: 'found', answer: 'Yes.', cited: ['c1'], low_confidence: false, cached: false, done, total: 2,
})

afterEach(() => vi.restoreAllMocks())

describe('useChatStream, Ask each paper', () => {
  it('collects each reading before the answer and asks with each_paper', async () => {
    const askChat = vi.spyOn(api, 'askChat').mockImplementation(async () =>
      sse(['reading', reading('Smith 2021', 1)], ['reading', reading('Lee 2020', 2)],
        ['sources', { sources: [], whole_paper: false, notes: [], notes_used: null, notes_total: null }],
        ['token', { text: 'Both.' }], ['done', { output_id: 'o1', model: 'm', connection_name: 'c', prompt_version: 1, cited: [], skill_label: null, lens: 'full' }]),
    )
    const hook = renderHook(() => useChatStream({ kind: 'workspace', id: 'w1' }, null, null))

    await act(() => hook.result.current.ask('Compare them', null, true))

    expect(askChat).toHaveBeenCalledWith({ kind: 'workspace', id: 'w1' }, 'Compare them', null, null, null, expect.anything(), true)
    expect(hook.result.current.stream.readings.map((r) => r.label)).toEqual(['Smith 2021', 'Lee 2020'])
    expect(hook.result.current.stream).toMatchObject({ status: 'done', eachPaper: true })
  })

  it('asks again in the same mode on Retry', async () => {
    const askChat = vi.spyOn(api, 'askChat').mockImplementation(async () => sse(['error', { message: 'Busy.', retryable: true }]))
    const hook = renderHook(() => useChatStream({ kind: 'workspace', id: 'w1' }, null, null))
    await act(() => hook.result.current.ask('Compare them', null, true))

    await act(() => hook.result.current.retry())

    expect(askChat).toHaveBeenLastCalledWith({ kind: 'workspace', id: 'w1' }, 'Compare them', null, null, null, expect.anything(), true)
  })
})
