import { describe, expect, it } from 'vitest'
import { parseRoute, readerHref } from './route'

const id = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'

describe('parseRoute', () => {
  it('opens the reader for a paper id, on the Notes tab by default', () => {
    expect(parseRoute(readerHref(id))).toEqual({ name: 'reader', paperId: id, tab: 'notes' })
  })

  it('keeps the Chat tab in the hash', () => {
    expect(readerHref(id, 'chat')).toBe(`#/papers/${id}?tab=chat`)
    expect(parseRoute(readerHref(id, 'chat'))).toEqual({ name: 'reader', paperId: id, tab: 'chat' })
  })

  it('treats an unknown tab as Notes', () => {
    expect(parseRoute(`#/papers/${id}?tab=graph`)).toEqual({ name: 'reader', paperId: id, tab: 'notes' })
  })

  it('falls back to the library for anything else', () => {
    expect(parseRoute('')).toEqual({ name: 'library' })
    expect(parseRoute('#/')).toEqual({ name: 'library' })
    expect(parseRoute('#/papers/not-an-id')).toEqual({ name: 'library' })
  })
})
