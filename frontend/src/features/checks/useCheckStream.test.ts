// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { CHAT_MODEL_KEY } from '@/features/chat/chatModel'
import { useCheckStream } from './useCheckStream'

const invalidate = vi.fn()
vi.mock('./queries', () => ({ useInvalidateChecks: () => invalidate }))
vi.mock('@/api/queries', () => ({
  useChatModels: () => ({ data: [{ id: 'm1', is_default: true }, { id: 'm2', is_default: false }] }),
}))

const source = { label: 'C1', page: 1, bbox: [[0, 0, 1, 1]] }
const sse = (...events: [string, unknown][]) =>
  new Response(events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(''), {
    headers: { 'content-type': 'text/event-stream' },
  })
const missing = { verdict: 'missing', text: 'the dataset [C1]' }

function start(response: Response | Promise<Response>) {
  const spy = vi.spyOn(api, 'checkNote').mockImplementation(() => Promise.resolve(response))
  return { spy, hook: renderHook(() => useCheckStream('n1', 'p1', 'summary')) }
}

beforeEach(() => {
  invalidate.mockReset()
  localStorage.clear()
})
afterEach(() => vi.restoreAllMocks())

describe('useCheckStream', () => {
  it('streams the sources and one line per token, then ends done and refetches the checks', async () => {
    const { hook } = start(
      sse(['sources', { sources: [source] }], ['token', { text: 'Missing: the dataset [C1]\n' }], ['token', { text: 'Supported: the loss [C1]\n' }], ['done', { output_id: 'o1' }]),
    )
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({
      status: 'done',
      sources: [source],
      lines: [missing, { verdict: 'supported', text: 'the loss [C1]' }],
      problem: null,
    })
    await waitFor(() => expect(invalidate).toHaveBeenCalled())
  })

  it('sends the default model, or the remembered pick, without confirming', async () => {
    const first = start(sse(['done', { output_id: 'o' }]))
    await act(() => first.hook.result.current.run())
    expect(first.spy).toHaveBeenCalledWith('n1', 'm1', false, expect.anything())
    localStorage.setItem(CHAT_MODEL_KEY, 'm2')
    const second = start(sse(['done', { output_id: 'o' }]))
    await act(() => second.hook.result.current.run())
    expect(second.spy).toHaveBeenCalledWith('n1', 'm2', false, expect.anything())
  })

  it('asks first on a remote model, naming its host, and sends confirm_remote on run(true)', async () => {
    const refusal = () => Response.json({ detail: 'remote_model_needs_confirm', model: 'Claude', host: 'api.anthropic.com' }, { status: 409 })
    const { spy, hook } = start(refusal())
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({ status: 'confirm', host: 'api.anthropic.com', problem: null })
    spy.mockResolvedValue(sse(['done', { output_id: 'o' }]))
    await act(() => hook.result.current.run(true))
    expect(spy).toHaveBeenLastCalledWith('n1', 'm1', true, expect.anything())
    expect(hook.result.current.stream.status).toBe('done')
  })

  it('resends the model the refusal was for, even if the pick changed while the dialog was open', async () => {
    const { spy, hook } = start(Response.json({ detail: 'remote_model_needs_confirm', host: 'h' }, { status: 409 }))
    await act(() => hook.result.current.run())
    localStorage.setItem(CHAT_MODEL_KEY, 'm2')
    spy.mockResolvedValue(sse(['done', { output_id: 'o' }]))
    await act(() => hook.result.current.run(true))
    expect(spy.mock.calls.map(([, model, confirm]) => [model, confirm])).toEqual([['m1', false], ['m1', true]])
  })

  it('words a lens_empty refusal for the kind it was given', async () => {
    vi.spyOn(api, 'checkNote').mockResolvedValue(Response.json({ detail: 'lens_empty' }, { status: 409 }))
    const hook = renderHook(() => useCheckStream('n1', 'p1', 'reconstruction'))
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream.problem?.message).toContain('How they did it')
  })

  it('sends nothing when the confirmation is cancelled', async () => {
    const { spy, hook } = start(Response.json({ detail: 'remote_model_needs_confirm', host: 'h' }, { status: 409 }))
    await act(() => hook.result.current.run())
    act(() => hook.result.current.cancelConfirm())
    expect(hook.result.current.stream).toMatchObject({ status: 'idle', host: null })
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it("ends in the server's error, keeping the lines", async () => {
    const { hook } = start(sse(['token', { text: 'Missing: the dataset [C1]\n' }], ['error', { message: 'The model failed.', retryable: true }]))
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({
      status: 'error',
      lines: [missing],
      problem: { message: 'The model failed.', retryable: true, reindex: false },
    })
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('says the check stopped when the stream ends without done', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { hook } = start(sse(['token', { text: 'Missing: the dataset [C1]\n' }]))
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({
      status: 'error',
      lines: [missing],
      problem: { message: 'The check stopped before it finished.', retryable: true },
    })
  })

  it('words a refusal before streaming from its code', async () => {
    const { hook } = start(Response.json({ detail: 'no_model' }, { status: 409 }))
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({
      status: 'error',
      problem: { message: 'Add a model in Settings to check your notes.', settings: true },
    })
  })

  it("says the API can't be reached when the request fails", async () => {
    vi.spyOn(api, 'checkNote').mockRejectedValue(new TypeError('Failed to fetch'))
    const hook = renderHook(() => useCheckStream('n1', 'p1', 'summary'))
    await act(() => hook.result.current.run())
    expect(hook.result.current.stream).toMatchObject({ status: 'error', problem: { message: "Can't reach the PaperLab API." } })
  })
})
