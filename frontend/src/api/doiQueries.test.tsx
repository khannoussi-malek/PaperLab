// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from './client'
import { useDoiCheck } from './queries'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('the DOI check posts only on demand, for the one manuscript', async () => {
  const done = { checked: 1, not_checked: 0, findings: [], counts: { error: 0, warning: 0, info: 0 } }
  const spy = vi.spyOn(api, 'runDoiCheck').mockResolvedValue(done)
  const { result } = renderHook(() => useDoiCheck(), { wrapper })
  expect(spy).not.toHaveBeenCalled()
  act(() => result.current.mutate('m1'))
  await waitFor(() => expect(result.current.data).toEqual(done))
  expect(spy).toHaveBeenCalledWith('m1')
})
