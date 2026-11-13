// @vitest-environment jsdom
import { renderHook } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { useStepCounts } from './useStepCounts'

const hit = (extra: object = {}) => ({ id: 'h', ...extra })

function mock(byStatus: Record<string, object[]>, saved: object[] = []) {
  vi.spyOn(queries, 'useSavedSearches').mockReturnValue({ data: saved } as any)
  vi.spyOn(queries, 'useSearchHits').mockImplementation(((_ws: string, _s?: string, status?: string) => ({
    data: { pages: [{ items: byStatus[status ?? ''] ?? [], next_cursor: null }] },
    hasNextPage: false,
  })) as any)
}

afterEach(() => vi.restoreAllMocks())

test('papers saved without a PDF count as waiting for a PDF, never as pending verdicts', () => {
  mock({ failed: [hit()], awaiting_pdf: [hit(), hit()], imported: [hit()], manual: [] })
  const { result } = renderHook(() => useStepCounts('ws-1'))
  expect(result.current).toEqual({ acquisition: 3, screening: 1 })
})

test('the Search tab counts what saved searches found since the reader last looked', () => {
  mock({}, [{ new_hits: 2 }, { new_hits: 0 }, { new_hits: 3 }])
  expect(renderHook(() => useStepCounts('ws-1')).result.current.search).toBe(5)
})

test('with nothing new the Search tab has no count', () => {
  mock({}, [{ new_hits: 0 }])
  expect(renderHook(() => useStepCounts('ws-1')).result.current.search).toBeUndefined()
})
