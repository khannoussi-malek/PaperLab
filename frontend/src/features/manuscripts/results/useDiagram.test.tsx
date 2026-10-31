// @vitest-environment jsdom
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type Diagram } from '@/api/client'
import { useDiagram } from './useDiagram'

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
)
const row = (status: Diagram['status'], o: Partial<Diagram> = {}) =>
  ({ id: 'd1', description: 'A to B', status, code: null, libraries: [], compiled: null, errors: [], labels_not_in_description: [], reason: null, model: null, ai: true, created_at: 't0', updated_at: 't1', ...o }) as Diagram
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

test('polls every 2 s only while the run is live, and not after unmount', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.spyOn(api, 'createDiagram').mockResolvedValue(row('queued'))
  const poll = vi.spyOn(api, 'diagram').mockResolvedValueOnce(row('running')).mockResolvedValue(row('done', { code: 'P', compiled: true }))
  const { result, unmount } = renderHook(() => useDiagram('m'), { wrapper })
  expect(poll).not.toHaveBeenCalled()
  await act(() => result.current.create('A to B', false))
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await waitFor(() => expect(result.current.diagram?.status).toBe('done'))
  const calls = poll.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(poll.mock.calls.length).toBe(calls)

  poll.mockResolvedValue(row('running'))
  vi.spyOn(api, 'setDiagramCode').mockResolvedValue(row('queued', { code: 'Q' }))
  await act(() => result.current.editCode('Q'))
  unmount()
  const n = poll.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(poll.mock.calls.length).toBe(n)
})

test('create sends confirm_remote; edit, cancel, regenerate and discard name the run', async () => {
  const create = vi.spyOn(api, 'createDiagram').mockResolvedValueOnce(row('done', { code: 'P', compiled: true })).mockResolvedValue(row('queued', { id: 'd2' }))
  vi.spyOn(api, 'diagram').mockImplementation(async (_m, id) => row('running', { id }))
  const put = vi.spyOn(api, 'setDiagramCode').mockResolvedValue(row('queued', { code: 'Q' }))
  const cancel = vi.spyOn(api, 'cancelDiagram').mockResolvedValue(row('failed', { reason: 'cancelled' }))
  const del = vi.spyOn(api, 'deleteDiagram').mockResolvedValue(undefined)
  const { result } = renderHook(() => useDiagram('m'), { wrapper })
  await act(() => result.current.create('  A to B ', true))
  expect(create).toHaveBeenCalledWith('m', { description: 'A to B', confirm_remote: true })
  await act(() => result.current.editCode('Q'))
  expect(put).toHaveBeenCalledWith('m', 'd1', 'Q')
  expect(result.current.diagram?.status).toBe('queued')
  await act(() => result.current.cancel())
  expect(cancel).toHaveBeenCalledWith('m', 'd1')
  await act(() => result.current.regenerate())
  expect(create).toHaveBeenLastCalledWith('m', { description: 'A to B', confirm_remote: true })
  expect(del).toHaveBeenCalledWith('m', 'd1') // the old draft goes
  expect(result.current.diagram?.id).toBe('d2')
  await act(() => result.current.discard())
  expect(del).toHaveBeenLastCalledWith('m', 'd2')
  expect(result.current.diagram).toBeNull()
})
