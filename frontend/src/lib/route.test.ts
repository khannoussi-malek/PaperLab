import { describe, expect, it } from 'vitest'
import { parseRoute, readerHref } from './route'

describe('parseRoute', () => {
  it('opens the reader for a paper id', () => {
    const id = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'
    expect(parseRoute(readerHref(id))).toEqual({ name: 'reader', paperId: id })
  })

  it('falls back to the library for anything else', () => {
    expect(parseRoute('')).toEqual({ name: 'library' })
    expect(parseRoute('#/')).toEqual({ name: 'library' })
    expect(parseRoute('#/papers/not-an-id')).toEqual({ name: 'library' })
  })
})
