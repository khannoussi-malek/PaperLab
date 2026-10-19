// @vitest-environment jsdom
import { renderHook } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { useStepCounts } from './useStepCounts'

const hit = (extra: object = {}) => ({ id: 'h', ...extra })

function mock(byStatus: Record<string, object[]>) {
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
