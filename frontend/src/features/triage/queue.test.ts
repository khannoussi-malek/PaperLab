import { describe, expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { buildQueue, countsByPile, current, isDone, newSince, orderPapers, progress, queueReducer, type DoneEntry, type QueueState } from './queue'

let n = 0
const paper = (o: Partial<Paper> & { id: string }): Paper =>
  ({ title: o.id, authors: [], year: null, cited_by_count: null, status: 'ready', has_pdf: true, triage: null, reading_pass: 0,
    created_at: `2026-01-0${(n++ % 9) + 1}T00:00:00Z`, ...o }) as Paper
const ids = (ps: Paper[]) => ps.map((p) => p.id)
const opts = { order: 'list', seed: 1, includeDecided: false, exclude: new Set<string>() } as const

describe('buildQueue', () => {
  const ps = [paper({ id: 'a' }), paper({ id: 'b', triage: 'keep' }), paper({ id: 'c' })]
  it('defaults to undecided papers of the given array', () => {
    expect(buildQueue(ps, opts).ids).toEqual(['a', 'c'])
  })
  it('include decided adds the decided ones', () => {
    expect(buildQueue(ps, { ...opts, includeDecided: true }).ids).toEqual(['a', 'b', 'c'])
  })
  it('excludes and counts non-ready papers; keeps a no-pdf embedding paper; counts failed apart', () => {
    const list = [
      paper({ id: 'r' }),
      paper({ id: 'q', status: 'embedding', has_pdf: true }),
      paper({ id: 'np', status: 'embedding', has_pdf: false }),
      paper({ id: 'f', status: 'failed' }),
    ]
    expect(buildQueue(list, opts)).toEqual({ ids: ['r', 'np'], notReady: 1, failed: 1 })
  })
  it('skips excluded ids', () => {
    expect(buildQueue(ps, { ...opts, exclude: new Set(['a']) }).ids).toEqual(['c'])
  })
})

describe('orderPapers', () => {
  const list = [
    paper({ id: 'x', title: 'banana', year: 2020, cited_by_count: 5, created_at: '2026-03-01T00:00:00Z' }),
    paper({ id: 'y', title: 'Äpfel', year: null, cited_by_count: null, created_at: '2026-01-01T00:00:00Z' }),
    paper({ id: 'z', title: 'cherry', year: 2018, cited_by_count: 9, created_at: '2026-02-01T00:00:00Z' }),
    paper({ id: 'w', title: 'cherry', year: 2020, cited_by_count: 5, created_at: '2026-02-01T00:00:00Z' }),
  ]
  const by = (o: Parameters<typeof orderPapers>[1]) => ids(orderPapers(list, o, 7))
  it('oldest / newest by created_at, ties by list position', () => {
    expect(by('oldest')).toEqual(['y', 'z', 'w', 'x'])
    expect(by('newest')).toEqual(['x', 'z', 'w', 'y'])
  })
  it('list keeps the given order', () => expect(by('list')).toEqual(['x', 'y', 'z', 'w']))
  it('title is locale aware', () => expect(by('title')).toEqual(['y', 'x', 'z', 'w']))
  it('year both ways with unknown last', () => {
    expect(by('year_desc')).toEqual(['x', 'w', 'z', 'y'])
    expect(by('year_asc')).toEqual(['z', 'x', 'w', 'y'])
  })
  it('cited most first with null last', () => expect(by('cited')).toEqual(['z', 'x', 'w', 'y']))
  it('shuffle is repeatable per seed and differs between seeds', () => {
    const big = Array.from({ length: 12 }, (_, i) => paper({ id: `p${i}` }))
    const a = ids(orderPapers(big, 'shuffle', 1))
    expect(ids(orderPapers(big, 'shuffle', 1))).toEqual(a)
    expect(ids(orderPapers(big, 'shuffle', 2))).not.toEqual(a)
    expect([...a].sort()).toEqual(ids(big).sort())
  })
})

const entry = (id: string, pile: DoneEntry['pile'] = 'skim', extra: Partial<DoneEntry> = {}): DoneEntry =>
  ({ id, clientId: `c-${id}`, pile, before: { triage: null, pass: 0 }, eventId: null, status: 'pending', ...extra })
const started = (list: string[] = ['a', 'b', 'c', 'd']): QueueState => queueReducer(undefined, { type: 'start', ids: list, seed: 3, order: 'list' })

describe('queueReducer', () => {
  it('start sets the stack and total', () => {
    const s = started()
    expect(current(s)).toBe('a')
    expect(progress(s)).toEqual({ decided: 0, skipped: 0, total: 4 })
  })
  it('decide removes from unseen and pushes done', () => {
    const s = queueReducer(started(), { type: 'decide', entry: entry('a') })
    expect(s.unseen).toEqual(['b', 'c', 'd'])
    expect(s.done.map((d) => d.id)).toEqual(['a'])
    expect(progress(s).decided).toBe(1)
  })
  it('skip goes to skipped, not the back of unseen', () => {
    const s = queueReducer(started(), { type: 'decide', entry: entry('a', 'skip') })
    expect(s.unseen).toEqual(['b', 'c', 'd'])
    expect(s.skipped).toEqual(['a'])
    expect(progress(s)).toEqual({ decided: 0, skipped: 1, total: 4 })
  })
  it('settle marks the entry saved', () => {
    const s = queueReducer(queueReducer(started(), { type: 'decide', entry: entry('a') }), { type: 'settle', clientId: 'c-a', eventId: 'e1' })
    expect(s.done[0]).toMatchObject({ status: 'saved', eventId: 'e1' })
  })
  it('undo twice walks back in order and restores a skipped card', () => {
    let s = started()
    s = queueReducer(s, { type: 'decide', entry: entry('a') })
    s = queueReducer(s, { type: 'decide', entry: entry('b', 'skip') })
    s = queueReducer(s, { type: 'undo' })
    expect(current(s)).toBe('b')
    expect(s.skipped).toEqual([])
    s = queueReducer(s, { type: 'undo' })
    expect(s.unseen).toEqual(['a', 'b', 'c', 'd'])
    expect(s.done).toEqual([])
  })
  it('fail puts the card back above later cards and drops the entry; idempotent', () => {
    let s = queueReducer(started(), { type: 'decide', entry: entry('a') })
    s = queueReducer(s, { type: 'fail', clientId: 'c-a' })
    expect(s.unseen).toEqual(['a', 'b', 'c', 'd'])
    expect(s.done).toEqual([])
    expect(queueReducer(s, { type: 'fail', clientId: 'c-a' })).toEqual(s)
  })
  it('undoFailed puts the entry back and removes the card from the top', () => {
    const e = entry('a')
    let s = queueReducer(queueReducer(started(), { type: 'decide', entry: e }), { type: 'undo' })
    s = queueReducer(s, { type: 'undoFailed', entry: e })
    expect(s.unseen).toEqual(['b', 'c', 'd'])
    expect(s.done).toEqual([e])
  })
  it('undoRefused drops the entry and removes the card', () => {
    const e = entry('a')
    let s = queueReducer(queueReducer(started(), { type: 'decide', entry: e }), { type: 'undo' })
    s = queueReducer(s, { type: 'undoRefused', entry: e })
    expect(s.unseen).toEqual(['b', 'c', 'd'])
    expect(s.done).toEqual([])
  })
  it('is frozen: a list reorder, refetch or upload changes nothing', () => {
    const s = started()
    const papers = [paper({ id: 'z' }), paper({ id: 'd' }), paper({ id: 'a' })]
    expect(queueReducer(s, { type: 'papers', papers } as never)).toBe(s)
  })
  it('reorder keeps the head and re-sorts the rest', () => {
    const papers = ['d', 'c', 'b', 'a'].map((id) => paper({ id }))
    const s = queueReducer(started(), { type: 'reorder', order: 'list', papers })
    expect(s.unseen).toEqual(['a', 'd', 'c', 'b'])
  })
  it('refreeze never resurrects a decided id and recounts the total', () => {
    let s = queueReducer(started(['a', 'b', 'c']), { type: 'decide', entry: entry('a') })
    s = queueReducer(s, { type: 'decide', entry: entry('b', 'skip') })
    const papers = ['a', 'b', 'c', 'd', 'e'].map((id) => paper({ id }))
    s = queueReducer(s, { type: 'refreeze', papers, opts: { order: 'list', seed: 3, includeDecided: false } })
    expect(s.unseen).toEqual(['c', 'd', 'e'])
    expect(s.skipped).toEqual(['b'])
    expect(progress(s)).toEqual({ decided: 1, skipped: 1, total: 5 })
  })
  it('reviewSkipped makes the skipped the stack again in first-pass order', () => {
    let s = started(['a', 'b', 'c'])
    for (const id of ['a', 'b', 'c']) s = queueReducer(s, { type: 'decide', entry: entry(id, 'skip') })
    expect(isDone(s)).toBe(true)
    s = queueReducer(s, { type: 'reviewSkipped' })
    expect(s.unseen).toEqual(['a', 'b', 'c'])
    expect(s.skipped).toEqual([])
    s = queueReducer(s, { type: 'decide', entry: entry('a', 'later') })
    s = queueReducer(s, { type: 'undo' })
    expect(s.unseen).toEqual(['a', 'b', 'c'])
  })
  it('countsByPile counts the done entries', () => {
    let s = queueReducer(started(), { type: 'decide', entry: entry('a', 'later') })
    s = queueReducer(s, { type: 'decide', entry: entry('b', 'later') })
    expect(countsByPile(s)).toMatchObject({ later: 2, skim: 0 })
  })
  it('progress leaves out a failed or undone decision', () => {
    let s = queueReducer(started(), { type: 'decide', entry: entry('a') })
    s = queueReducer(s, { type: 'decide', entry: entry('b') })
    s = queueReducer(s, { type: 'fail', clientId: 'c-a' })
    s = queueReducer(s, { type: 'undo' })
    expect(progress(s).decided).toBe(0)
  })
})

describe('newSince', () => {
  it('counts only new, ready, undecided papers', () => {
    const s = queueReducer(started(['a', 'b']), { type: 'decide', entry: entry('a') })
    const papers = [paper({ id: 'a' }), paper({ id: 'b' }), paper({ id: 'n1' }), paper({ id: 'n2', triage: 'keep' }), paper({ id: 'n3', status: 'embedding' })]
    expect(newSince(s, papers, { includeDecided: false })).toBe(1)
  })
})
