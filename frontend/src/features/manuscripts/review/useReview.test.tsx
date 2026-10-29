// @vitest-environment jsdom
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type ReviewState } from '@/api/client'
import { reviewStartError, useCiteProposals, useReview } from './useReview'

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
)
const state = (status: string): ReviewState => ({ run: { id: 'r1', status } as ReviewState['run'], items: [], dismissed: [] })
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

test('polls while running, stops when done, and on unmount', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const spy = vi.spyOn(api, 'reviewState').mockResolvedValueOnce(state('running')).mockResolvedValue(state('done'))
  const { result, unmount } = renderHook(() => useReview('m', 'main.tex'), { wrapper })
  await waitFor(() => expect(result.current.run?.status).toBe('running'))
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await waitFor(() => expect(result.current.run?.status).toBe('done'))
  const calls = spy.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(spy.mock.calls.length).toBe(calls)

  spy.mockResolvedValue(state('running'))
  const second = renderHook(() => useReview('m', 'other.tex'), { wrapper })
  await waitFor(() => expect(second.result.current.run?.status).toBe('running'))
  second.unmount()
  const n = spy.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(spy.mock.calls.length).toBe(n)
  unmount()
})

test('start errors map to warm copy', () => {
  const e = (code: string) => new ApiError(code, 422, { detail: code })
  expect(reviewStartError(e('too_many_claims'))).toBe("That's more than 30 citations to check at once. Select a smaller part and try again.")
  expect(reviewStartError(e('no_model'))).toBe('Add a model in Settings to run the reviewer.')
  expect(reviewStartError(e('review_running'))).toBe('A check is already running.')
  expect(reviewStartError(e('file_changed'))).toBe('The file changed. Try again.')
})

test('start sends the selection and surfaces the mapped error', async () => {
  vi.spyOn(api, 'reviewState').mockResolvedValue({ run: null, items: [], dismissed: [] })
  const start = vi.spyOn(api, 'startReview').mockRejectedValue(new ApiError('x', 422, { detail: 'too_many_claims' }))
  const { result } = renderHook(() => useReview('m', 'main.tex'), { wrapper })
  await waitFor(() => expect(result.current.isLoading).toBe(false))
  await act(() => result.current.start('t0', { from: 1, to: 9 }).catch(() => undefined))
  expect(start).toHaveBeenCalledWith('m', expect.objectContaining({ file: 'main.tex', base: 't0', from: 1, to: 9 }))
  await waitFor(() => expect(result.current.startError).toMatch(/more than 30 citations/))
})

test('proposals: verdict papers first, then passages, three at most; polling stops', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const P = (n: string) => ({ paper_id: n, key: `k${n}`, passages: [{ chunk_id: `c${n}`, page: 1, text: `text ${n}` }] })
  vi.spyOn(api, 'findEvidence').mockResolvedValue({ sentence_hash: 'h', verdicts: 'queued', papers: [P('1'), P('2'), P('3'), P('4')] })
  const row = (id: string, status: string, verdict: string | null) => ({ paper_id: id, rank: 1, status, verdict, reason: null, quote: `quote ${id}`, page: 1, output_id: null })
  const rows = vi.spyOn(api, 'evidenceRows')
    .mockResolvedValueOnce([row('1', 'running', null)] as never)
    .mockResolvedValue([row('1', 'done', 'not_supported'), row('2', 'done', 'not_addressed'), row('3', 'done', 'partially_supported'), row('4', 'done', 'supported')] as never)
  const { result, unmount } = renderHook(() => useCiteProposals('m', 'A claim here.'), { wrapper })
  act(() => result.current.ask())
  await waitFor(() => expect(rows).toHaveBeenCalled())
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await waitFor(() => expect(result.current.pending).toBe(false))
  expect(result.current.proposals.map((p) => [p.key, p.verdict, p.quote])).toEqual([
    ['k3', 'partially_supported', 'quote 3'], ['k4', 'supported', 'quote 4'], ['k1', 'passage', 'text 1'],
  ])
  const n = rows.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(rows.mock.calls.length).toBe(n)
  unmount()
})

test('no matching paper says so', async () => {
  vi.spyOn(api, 'findEvidence').mockResolvedValue({ sentence_hash: 'h', verdicts: 'unavailable', papers: [] })
  const { result } = renderHook(() => useCiteProposals('m', 'A claim here.'), { wrapper })
  act(() => result.current.ask())
  await waitFor(() => expect(result.current.message).toBe('No paper in this workspace speaks to this.'))
})
