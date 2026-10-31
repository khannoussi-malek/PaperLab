// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, isConflict } from './client'
import { useTriageSummary } from './queries'

afterEach(() => vi.unstubAllGlobals())
const stub = (status: number, body: unknown) => {
  const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', f)
  return f
}

describe('triage calls', () => {
  it('decideTriage posts the body', async () => {
    const f = stub(200, { paper: {}, event: {} })
    const body = { pile: 'skim', session_id: 's', pdf_opened: false } as const
    await api.decideTriage('p1', body)
    expect(f).toHaveBeenCalledWith('/api/papers/p1/triage-decisions', expect.objectContaining({ method: 'POST', body: JSON.stringify(body) }))
  })
  it('undoTriage posts to the event', async () => {
    const f = stub(200, { paper: {}, event: {} })
    await api.undoTriage('e1')
    expect(f).toHaveBeenCalledWith('/api/triage-events/e1/undo', expect.objectContaining({ method: 'POST' }))
  })
  it('triageSummary gets by session', async () => {
    const f = stub(200, { decided: 0 })
    await api.triageSummary('s 1')
    expect(f).toHaveBeenCalledWith('/api/triage-summary?session_id=s%201', undefined)
  })
  it('an undo 409 maps to the conflict helper', async () => {
    stub(409, { detail: 'changed_since' })
    const e = await api.undoTriage('e1').catch((x: unknown) => x)
    expect(isConflict(e, 'changed_since')).toBe(true)
    expect(isConflict(e, 'already_undone')).toBe(false)
    expect(isConflict(new Error('x'), 'changed_since')).toBe(false)
  })
})

describe('useTriageSummary', () => {
  const wrap = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }, children)
  it('is disabled until enabled', async () => {
    const f = stub(200, { decided: 1 })
    const off = renderHook(() => useTriageSummary('s', false), { wrapper: wrap })
    expect(off.result.current.fetchStatus).toBe('idle')
    expect(f).not.toHaveBeenCalled()
    const on = renderHook(() => useTriageSummary('s', true), { wrapper: wrap })
    await waitFor(() => expect(on.result.current.data).toEqual({ decided: 1 }))
  })
})
