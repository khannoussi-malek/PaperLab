import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import { createWriter } from './triageWriter'

const deferred = <T,>() => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const flush = () => new Promise((r) => setTimeout(r, 0))
const e = (id: string) => ({ id, clientId: `c-${id}` })

function setup() {
  const posts: { id: string; d: ReturnType<typeof deferred<{ eventId: string }>> }[] = []
  const undos: { eventId: string; d: ReturnType<typeof deferred<unknown>> }[] = []
  const w = createWriter({
    post: (entry: ReturnType<typeof e>) => { const d = deferred<{ eventId: string }>(); posts.push({ id: entry.id, d }); return d.promise },
    undo: (eventId: string) => { const d = deferred<unknown>(); undos.push({ eventId, d }); return d.promise },
  })
  return { w, posts, undos }
}

describe('createWriter', () => {
  it('sends strictly one at a time, in order', async () => {
    const { w, posts } = setup()
    const a = w.decide(e('a'))
    const b = w.decide(e('b'))
    const c = w.decide(e('c'))
    await flush()
    expect(posts.map((p) => p.id)).toEqual(['a'])
    posts[0].d.resolve({ eventId: 'ea' })
    await a
    await flush()
    expect(posts.map((p) => p.id)).toEqual(['a', 'b'])
    posts[1].d.resolve({ eventId: 'eb' })
    await b
    await flush()
    expect(posts.map((p) => p.id)).toEqual(['a', 'b', 'c'])
    posts[2].d.resolve({ eventId: 'ec' })
    expect(await c).toEqual({ status: 'saved', eventId: 'ec' })
  })

  it('sends an undo issued while the decide is pending after it, with the reply event id', async () => {
    const { w, posts, undos } = setup()
    const d = w.decide(e('a'))
    const u = w.undo(e('a'))
    await flush()
    expect(undos).toHaveLength(0)
    posts[0].d.resolve({ eventId: 'ea' })
    await d
    await flush()
    expect(undos.map((x) => x.eventId)).toEqual(['ea'])
    undos[0].d.resolve({})
    expect((await u).status).toBe('saved')
  })

  it('an undo after a failed decide is a noop and sends nothing; later writes still go', async () => {
    const { w, posts, undos } = setup()
    const b = w.decide(e('b'))
    const ub = w.undo(e('b'))
    const c = w.decide(e('c'))
    await flush()
    posts[0].d.reject(new Error('offline'))
    expect((await b).status).toBe('failed')
    expect(await ub).toEqual({ status: 'noop' })
    await flush()
    expect(undos).toHaveLength(0)
    expect(posts.map((p) => p.id)).toEqual(['b', 'c'])
    posts[1].d.resolve({ eventId: 'ec' })
    expect((await c).status).toBe('saved')
  })

  it('a 409 changed_since on undo is refused; other errors are failed', async () => {
    const { w, posts, undos } = setup()
    const d1 = w.decide(e('a'))
    await flush()
    posts[0].d.resolve({ eventId: 'ea' })
    await d1
    const u1 = w.undo(e('a'))
    await flush()
    undos[0].d.reject(new ApiError('changed', 409, { detail: 'changed_since' }))
    expect(await u1).toEqual({ status: 'refused' })

    const d2 = w.decide(e('b'))
    await flush()
    posts[1].d.resolve({ eventId: 'eb' })
    await d2
    const u2 = w.undo(e('b'))
    await flush()
    undos[1].d.reject(new Error('boom'))
    expect((await u2).status).toBe('failed')
  })
})
