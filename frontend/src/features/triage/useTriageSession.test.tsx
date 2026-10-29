// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, StrictMode, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, type Paper, type TriageDecision, type TriageDecisionIn } from '@/api/client'
import { closeSession } from './sessionId'
import { current, isDone, progress } from './queue'
import { useTriageSession } from './useTriageSession'

const clock = { card_ms: 1000, pdf_ms: 0, pdf_opened: false }
const mk = (id: string): Paper =>
  ({ id, title: id, authors: [], year: null, cited_by_count: null, status: 'ready', has_pdf: true, triage: null, reading_pass: 0,
    created_at: "2026-01-01T00:00:00Z" }) as unknown as Paper
const papers = ['a', 'b', 'c', 'd'].map(mk)

type Call = { paperId: string; body: TriageDecisionIn; resolve: () => void; reject: (e: unknown) => void }
let calls: Call[]
let undoCalls: { eventId: string; resolve: () => void; reject: (e: unknown) => void }[]
const flush = () => act(() => new Promise<void>((r) => setTimeout(r, 0)))

beforeEach(() => {
  calls = []
  undoCalls = []
  sessionStorage.clear()
  vi.spyOn(api, 'decideTriage').mockImplementation(
    (paperId, body) =>
      new Promise<TriageDecision>((resolve, reject) => {
        calls.push({ paperId, body, resolve: () => resolve({ event: { id: `e-${body.client_id}` } } as TriageDecision), reject })
      }),
  )
  vi.spyOn(api, 'undoTriage').mockImplementation(
    (eventId) =>
      new Promise<TriageDecision>((resolve, reject) => {
        undoCalls.push({ eventId, resolve: () => resolve({} as TriageDecision), reject })
      }),
  )
})
afterEach(() => vi.restoreAllMocks())

type Props = { filterKey: string; queueFrom: Paper[]; library: Paper[]; libraryReady: boolean }
const base = (ps: Paper[] = papers, filterKey = 'f1'): Props => ({ filterKey, queueFrom: ps, library: ps, libraryReady: true })

function setup(extra: { filterKey?: string; ps?: Paper[]; strict?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => {
    const inner = createElement(QueryClientProvider, { client }, children)
    return extra.strict ? createElement(StrictMode, null, inner) : inner
  }
  return renderHook(
    (p: Props) => useTriageSession({ scope: 'all', ...p, order: 'list', includeDecided: false }),
    { wrapper, initialProps: base(extra.ps, extra.filterKey) },
  )
}
const decide = (h: ReturnType<typeof setup>, pile: 'read_closely' | 'skim' | 'not_relevant' | 'skip' = 'skim', reason?: string) =>
  act(() => h.result.current.decide(pile, { reason, clock }))
const send = async (i: number) => { await act(async () => calls[i].resolve()); await flush() }

describe('useTriageSession ordering', () => {
  it('three decides leave the screen at once, progress reads 3 before any reply, writes go one at a time', async () => {
    const h = setup()
    decide(h); decide(h); decide(h)
    await flush()
    expect(h.result.current.top?.id).toBe('d')
    expect(progress(h.result.current.state).decided).toBe(3)
    expect(calls.map((c) => c.paperId)).toEqual(['a'])
    await send(0)
    expect(calls.map((c) => c.paperId)).toEqual(['a', 'b'])
    await send(1)
    expect(calls.map((c) => c.paperId)).toEqual(['a', 'b', 'c'])
  })

  it('U brings the card back at once and the undo request waits for the decide reply and its event id', async () => {
    const h = setup()
    decide(h)
    await flush()
    act(() => h.result.current.undo())
    expect(h.result.current.top?.id).toBe('a')
    await flush()
    expect(undoCalls).toHaveLength(0)
    await send(0)
    expect(undoCalls.map((u) => u.eventId)).toEqual([`e-${calls[0].body.client_id}`])
  })

  it('U twice: the second applies to the earlier card after the first finished', async () => {
    const h = setup()
    decide(h); decide(h)
    await flush()
    act(() => h.result.current.undo())
    act(() => h.result.current.undo())
    expect(current(h.result.current.state)).toBe('a')
    await send(0)
    expect(undoCalls).toHaveLength(0) // b's decide (queued second) goes next, its undo after it
    await send(1)
    expect(undoCalls).toHaveLength(1)
    expect(undoCalls[0].eventId).toBe(`e-${calls[1].body.client_id}`)
    await act(async () => undoCalls[0].resolve()); await flush()
    expect(undoCalls).toHaveLength(2)
    expect(undoCalls[1].eventId).toBe(`e-${calls[0].body.client_id}`)
  })

  it('a failed POST returns that card with an alert; Retry resends with the same client_id and no second card', async () => {
    const h = setup()
    decide(h); decide(h)
    await flush()
    await act(async () => calls[0].resolve()); await flush()
    await act(async () => calls[1].reject(new Error('offline'))); await flush()
    expect(h.result.current.top?.id).toBe('b')
    expect(progress(h.result.current.state).decided).toBe(1)
    expect(h.result.current.alert?.message).toContain("Couldn't save: offline")
    const firstClient = calls[1].body.client_id
    await act(async () => h.result.current.alert?.retry?.())
    await flush()
    expect(calls).toHaveLength(3)
    expect(calls[2].body.client_id).toBe(firstClient)
    expect(calls[2].paperId).toBe('b')
    await send(2)
    expect(progress(h.result.current.state).decided).toBe(2)
    expect(h.result.current.top?.id).toBe('c')
    expect(h.result.current.alert).toBeNull()
  })

  it('a queued undo for a failed decide sends nothing, offers no Retry, and the next POST still goes', async () => {
    const h = setup()
    decide(h); decide(h) // a, b
    await flush()
    act(() => h.result.current.undo()) // takes b back
    await flush()
    await act(async () => calls[0].resolve()); await flush() // a saved, b's POST goes next
    expect(calls.map((c) => c.paperId)).toEqual(['a', 'b'])
    await act(async () => calls[1].reject(new Error('offline'))); await flush()
    expect(undoCalls).toHaveLength(0)
    expect(h.result.current.alert).toBeNull()
    expect(h.result.current.top?.id).toBe('b')
    expect(progress(h.result.current.state).decided).toBe(1)
    expect(calls).toHaveLength(2)
  })

  it('a decide undone while its POST is pending, then failing: no alert, no retry, progress 0', async () => {
    const h = setup()
    decide(h)
    await flush()
    act(() => h.result.current.undo())
    await act(async () => calls[0].reject(new Error('offline'))); await flush()
    expect(h.result.current.alert).toBeNull()
    expect(progress(h.result.current.state).decided).toBe(0)
    expect(h.result.current.top?.id).toBe('a')
    expect(calls).toHaveLength(1)
    expect(undoCalls).toHaveLength(0)
  })

  it('decide, undo, decide again: the first POST failing leaves only the second decision', async () => {
    const h = setup()
    decide(h)
    await flush()
    act(() => h.result.current.undo())
    decide(h)
    await flush()
    await act(async () => calls[0].reject(new Error('offline'))); await flush()
    expect(h.result.current.alert).toBeNull()
    expect(progress(h.result.current.state).decided).toBe(1)
    expect(h.result.current.top?.id).toBe('b')
    expect(calls.map((c) => c.paperId)).toEqual(['a', 'a'])
    expect(calls[1].body.client_id).not.toBe(calls[0].body.client_id)
    await send(1)
    expect(progress(h.result.current.state).decided).toBe(1)
  })

  it('a paper deleted elsewhere leaves the session: total 2, deciding the others reaches done', async () => {
    const three = papers.slice(0, 3)
    const h = setup({ ps: three })
    expect(progress(h.result.current.state).total).toBe(3)
    h.rerender(base(three.filter((p) => p.id !== 'b')))
    expect(progress(h.result.current.state).total).toBe(2)
    decide(h); decide(h)
    await flush()
    expect(isDone(h.result.current.state)).toBe(true)
    expect(h.result.current.top).toBeNull()
    expect(progress(h.result.current.state)).toMatchObject({ decided: 2, total: 2 })
  })

  it('announces each new card after the decision; an undo announces alone', async () => {
    const h = setup()
    expect(h.result.current.announcement).toContain('Paper 1 of 4')
    decide(h)
    await flush()
    expect(h.result.current.announcement).toContain('1 of 4 done')
    expect(h.result.current.announcement).toContain('Paper 2 of 4')
    act(() => h.result.current.undo())
    await flush()
    expect(h.result.current.announcement).toContain('Decision undone')
    expect(h.result.current.announcement).not.toContain('Paper 1 of 4')
  })

  it('a 409 changed_since on undo drops the paper from the session with the elsewhere message', async () => {
    const h = setup()
    decide(h)
    await flush()
    await send(0)
    act(() => h.result.current.undo())
    await flush()
    await act(async () => undoCalls[0].reject(new ApiError('changed', 409, { detail: 'changed_since' })))
    await flush()
    expect(h.result.current.alert?.message).toBe('This paper was changed elsewhere since. Open it to change it.')
    expect(h.result.current.top?.id).not.toBe('a')
    expect(h.result.current.state.left).toEqual(['a'])
  })

  it('never sends a not-relevant decision without a reason', async () => {
    const h = setup()
    decide(h, 'not_relevant')
    await flush()
    expect(calls).toHaveLength(0)
    expect(h.result.current.top?.id).toBe('a')
    expect(h.result.current.alert?.message).toMatch(/reason/i)
  })

  it('skips are saved to the server, and reviewSkipped waits until nothing is pending', async () => {
    const h = setup()
    act(() => h.result.current.skip())
    await flush()
    expect(calls[0].body.pile).toBe('skip')
    expect(h.result.current.pending).toBe(1)
    act(() => h.result.current.reviewSkipped())
    expect(h.result.current.state.skipped).toEqual(['a'])
    await send(0)
    expect(h.result.current.pending).toBe(0)
    act(() => h.result.current.reviewSkipped())
    expect(h.result.current.state.skipped).toEqual([])
  })
})

describe('useTriageSession library and queue lists', () => {
  it('a decided paper that leaves queueFrom (the filter drops it) can still be undone and returns as top', async () => {
    const h = setup()
    decide(h)
    await flush()
    h.rerender({ ...base(), queueFrom: papers.filter((p) => p.id !== 'a') })
    expect(h.result.current.state.done.map((d) => d.id)).toEqual(['a'])
    act(() => h.result.current.undo())
    expect(h.result.current.top?.id).toBe('a')
    expect(progress(h.result.current.state)).toMatchObject({ decided: 0, total: 4 })
  })

  it('a library that is briefly empty and not ready vanishes nothing', async () => {
    const h = setup()
    h.rerender({ ...base(), library: [], libraryReady: false })
    expect(progress(h.result.current.state).total).toBe(4)
    expect(h.result.current.state.unseen).toHaveLength(4)
    h.rerender({ ...base(), library: [], libraryReady: true }) // still empty: never mass-vanish
    expect(h.result.current.state.unseen).toHaveLength(4)
  })

  it('a paper removed from a ready library vanishes', async () => {
    const h = setup()
    h.rerender({ ...base(), library: papers.filter((p) => p.id !== 'a') })
    expect(h.result.current.state.unseen).toEqual(['b', 'c', 'd'])
    expect(progress(h.result.current.state).total).toBe(3)
  })

  it('a failed undo can be retried: same event id, and Retry sends it again', async () => {
    const h = setup()
    decide(h)
    await flush()
    await send(0)
    act(() => h.result.current.undo())
    await flush()
    await act(async () => undoCalls[0].reject(new Error('offline'))); await flush()
    expect(h.result.current.alert?.message).toContain("Couldn't undo: offline")
    expect(h.result.current.top?.id).toBe('b') // the decision stands again
    await act(async () => h.result.current.alert?.retry?.()); await flush()
    expect(undoCalls).toHaveLength(2)
    expect(undoCalls[1].eventId).toBe(undoCalls[0].eventId)
    expect(h.result.current.top?.id).toBe('a')
  })

  it('under StrictMode a same-key rerender does not re-freeze (decisions and counts stay)', async () => {
    const h = setup({ strict: true })
    decide(h)
    await flush()
    h.rerender(base())
    expect(progress(h.result.current.state)).toMatchObject({ decided: 1, total: 4 })
    expect(h.result.current.state.unseen).toEqual(['b', 'c', 'd'])
  })
})

describe('useTriageSession session', () => {
  it('keeps the session id across a remount and refreeze on filterKey keeps the id and counts', async () => {
    const h = setup()
    const id = h.result.current.sessionId
    decide(h)
    await flush()
    h.rerender(base(papers, 'f2'))
    expect(h.result.current.sessionId).toBe(id)
    expect(progress(h.result.current.state).decided).toBe(1)
    h.unmount()
    expect(setup().result.current.sessionId).toBe(id)
    closeSession('all')
    expect(setup().result.current.sessionId).not.toBe(id)
  })
})
