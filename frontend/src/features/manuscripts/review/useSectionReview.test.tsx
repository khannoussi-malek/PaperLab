// @vitest-environment jsdom
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type SectionReview } from '@/api/client'
import { remoteHost } from './reviewModel'
import { sectionStartError, useSectionReview } from './useSectionReview'

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
)
const reviews = (status: string) => ({ reviews: [{ id: 'r1', status, section_hash: 'h' } as SectionReview] })
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

test('polls every 2 s only while a review is live, and not after unmount', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const spy = vi.spyOn(api, 'sectionReviews').mockResolvedValueOnce(reviews('queued')).mockResolvedValueOnce(reviews('running')).mockResolvedValue(reviews('done'))
  const { result, unmount } = renderHook(() => useSectionReview('m', 'main.tex'), { wrapper })
  await waitFor(() => expect(result.current.live).toBe(true))
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await waitFor(() => expect(result.current.reviews[0].status).toBe('done'))
  expect(result.current.live).toBe(false)
  const calls = spy.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(spy.mock.calls.length).toBe(calls)

  spy.mockResolvedValue(reviews('running'))
  const second = renderHook(() => useSectionReview('m', 'other.tex'), { wrapper })
  await waitFor(() => expect(second.result.current.live).toBe(true))
  second.unmount()
  const n = spy.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(spy.mock.calls.length).toBe(n)
  unmount()
})

test('each start error has its own words; the remote signal is not an error', () => {
  const e = (code: string, status = 422) => new ApiError(code, status, { detail: code })
  expect(sectionStartError(e('unknown_role'))).toBe('Pick what kind of section this is.')
  expect(sectionStartError(e('no_section'))).toBe('Put the cursor inside a section first.')
  expect(sectionStartError(e('section_too_long'))).toBe('That section is too long to review at once. Review it in parts.')
  expect(sectionStartError(e('no_model', 409))).toBe('Add a model in Settings to run the reviewer.')
  expect(sectionStartError(e('review_running', 409))).toBe('A review is already running.')
  expect(sectionStartError(e('file_changed', 409))).toBe('The file changed. Try again.')
  const remote = new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', model: 'Cloud · big', host: 'api.example.com' })
  expect(sectionStartError(remote)).toBeNull()
  expect(remoteHost(remote)).toBe('api.example.com')
  expect(remoteHost(e('no_model', 409))).toBeNull()
})

test('start sends file, base, cursor, role and confirm_remote; cancel names the review', async () => {
  vi.spyOn(api, 'sectionReviews').mockResolvedValue({ reviews: [] })
  const start = vi.spyOn(api, 'startSectionReview').mockResolvedValue({} as SectionReview)
  const cancel = vi.spyOn(api, 'cancelSectionReview').mockResolvedValue({} as SectionReview)
  const { result } = renderHook(() => useSectionReview('m', 'main.tex'), { wrapper })
  await act(() => result.current.start({ base: 't0', at: 42, role: 'method', confirmRemote: true }))
  expect(start).toHaveBeenCalledWith('m', { file: 'main.tex', base: 't0', at: 42, role: 'method', confirm_remote: true })
  await act(() => result.current.cancel('r9'))
  expect(cancel).toHaveBeenCalledWith('m', 'r9')
})
