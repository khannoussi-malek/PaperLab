// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { useBriefStream } from './useBriefStream'

const invalidate = vi.fn()
vi.mock('./queries', () => ({ useInvalidateBriefs: () => invalidate }))

const source = { label: 'C1', page: 1, bbox: [[0, 0, 1, 1]] }
const sse = (...events: [string, unknown][]) =>
  new Response(events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(''), {
    headers: { 'content-type': 'text/event-stream' },
  })

async function run(response: Response | Promise<Response>) {
  vi.spyOn(api, 'generateBrief').mockReturnValue(Promise.resolve(response))
  const hook = renderHook(() => useBriefStream('p1'))
  await act(() => hook.result.current.generate('key_ideas', 'Key ideas'))
  return hook.result.current.stream
}

beforeEach(() => invalidate.mockReset())
afterEach(() => vi.restoreAllMocks())

describe('useBriefStream', () => {
  it('streams the sources and text, then ends done with the saved id and refetches the briefs', async () => {
    const stream = await run(
      sse(['sources', { sources: [source] }], ['token', { text: 'The method ' }], ['token', { text: '[C1].' }], ['done', { output_id: 'o1' }]),
    )
    expect(stream).toMatchObject({ status: 'done', lens: 'key_ideas', outputId: 'o1', sources: [source], problem: null })
    expect(stream.segments).toEqual([{ kind: 'text', text: 'The method ' }, { kind: 'cite', label: 'C1' }, { kind: 'text', text: '.' }])
    await waitFor(() => expect(invalidate).toHaveBeenCalled())
  })

  it("ends in the server's error, keeping what was written", async () => {
    const stream = await run(sse(['sources', { sources: [source] }], ['token', { text: 'Half' }], ['error', { message: 'The model failed.', retryable: true }]))
    expect(stream).toMatchObject({ status: 'error', problem: { message: 'The model failed.', retryable: true, reindex: false } })
    expect(stream.segments).toEqual([{ kind: 'text', text: 'Half' }])
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('says the brief stopped when the stream ends without done', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const stream = await run(sse(['sources', { sources: [source] }], ['token', { text: 'Half' }]))
    expect(stream).toMatchObject({ status: 'error', problem: { message: 'The brief stopped before it finished.', retryable: true } })
    expect(stream.segments).toEqual([{ kind: 'text', text: 'Half' }])
  })

  it('words a refusal before streaming from its code', async () => {
    const stream = await run(Response.json({ detail: 'no_model' }, { status: 409 }))
    expect(stream).toMatchObject({
      status: 'error',
      segments: [],
      problem: { message: 'Add a model in Settings to write briefs.', retryable: false, settings: true },
    })
  })

  it("says the API can't be reached when the request fails", async () => {
    vi.spyOn(api, 'generateBrief').mockRejectedValue(new TypeError('Failed to fetch'))
    const hook = renderHook(() => useBriefStream('p1'))
    await act(() => hook.result.current.generate('key_ideas', 'Key ideas'))
    expect(hook.result.current.stream).toMatchObject({ status: 'error', problem: { message: "Can't reach the PaperLab API.", retryable: true } })
  })
})
