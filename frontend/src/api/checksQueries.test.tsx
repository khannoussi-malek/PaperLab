// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from './client'
import { useCheckBadge, useCheckList, useRunChecks } from './queries'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
const empty = { ran: ['a.one'], findings: [], counts: { error: 0, warning: 0, info: 0 } }
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('the badge runs only the cheap checks, and a save (an invalidation of the manuscript) refetches it', async () => {
  const spy = vi.spyOn(api, 'runChecks').mockResolvedValue(empty)
  renderHook(() => useCheckBadge('m', 't1'), { wrapper })
  await waitFor(() => expect(spy).toHaveBeenCalledWith('m', { cost: 'cheap' }))
  await act(async () => { await client.invalidateQueries({ queryKey: ['manuscripts', 'm'] }) }) // what useSaveManuscriptFile does
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
})

test('a new compile refetches the badge', async () => {
  const spy = vi.spyOn(api, 'runChecks').mockResolvedValue(empty)
  const { rerender } = renderHook((p: { at: string }) => useCheckBadge('m', p.at), { wrapper, initialProps: { at: 't1' } })
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
  rerender({ at: 't2' })
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
})

test('the old badge data stays while a refetch is in flight (no flicker)', async () => {
  let release!: () => void
  const spy = vi.spyOn(api, 'runChecks').mockResolvedValueOnce(empty).mockImplementationOnce(() => new Promise((r) => { release = () => r(empty) }))
  const { result, rerender } = renderHook((p: { at: string }) => useCheckBadge('m', p.at), { wrapper, initialProps: { at: 't1' } })
  await waitFor(() => expect(result.current.data).toEqual(empty))
  rerender({ at: 't2' })
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  expect(result.current.data).toEqual(empty) // placeholder, not undefined
  release()
})

test('Check runs every check (empty body)', async () => {
  const spy = vi.spyOn(api, 'runChecks').mockResolvedValue(empty)
  const { result } = renderHook(() => useRunChecks(), { wrapper })
  await act(async () => { await result.current.mutateAsync('m') })
  expect(spy).toHaveBeenCalledWith('m', {})
})

test('the check list is fetched once and a save does not refetch it', async () => {
  const spy = vi.spyOn(api, 'listManuscriptChecks').mockResolvedValue([{ name: 'a.one', cost: 'cheap', description: 'D' }])
  const { result } = renderHook(() => useCheckList('m'), { wrapper })
  await waitFor(() => expect(result.current.data?.[0].description).toBe('D'))
  await act(async () => { await client.invalidateQueries({ queryKey: ['manuscripts', 'm'] }) })
  expect(spy).toHaveBeenCalledTimes(1)
})

test('api.runChecks posts JSON to the run route', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(empty), { status: 200 }))
  await api.runChecks('m', { cost: 'cheap' })
  const [url, init] = fetchSpy.mock.calls[0]
  expect(url).toBe('/api/manuscripts/m/checks/run')
  expect(init).toMatchObject({ method: 'POST', body: JSON.stringify({ cost: 'cheap' }) })
})
