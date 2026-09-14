import { describe, expect, it } from 'vitest'
import { chunkHref, noteHref, parseRoute, readerHref, workspaceHref } from './route'

const id = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'
const other = '9b2d4c1e-7f3a-4e55-8c21-0d6b5a4f3e21'

describe('parseRoute', () => {
  it('opens the reader for a paper id, on the Notes tab by default', () => {
    expect(parseRoute(readerHref(id))).toEqual({ name: 'reader', paperId: id, tab: 'notes', target: null })
  })

  it('keeps the Chat tab in the hash', () => {
    expect(readerHref(id, 'chat')).toBe(`#/papers/${id}?tab=chat`)
    expect(parseRoute(readerHref(id, 'chat'))).toEqual({ name: 'reader', paperId: id, tab: 'chat', target: null })
  })

  it('treats an unknown tab as Notes', () => {
    expect(parseRoute(`#/papers/${id}?tab=graph`)).toEqual({ name: 'reader', paperId: id, tab: 'notes', target: null })
  })

  it('reads a chunk target with its page, for the reader to flash once', () => {
    expect(chunkHref(id, other, 3)).toBe(`#/papers/${id}?chunk=${other}&page=3`)
    expect(parseRoute(chunkHref(id, other, 3))).toEqual({
      name: 'reader',
      paperId: id,
      tab: 'notes',
      target: { kind: 'chunk', id: other, page: 3 },
    })
  })

  it('reads a note target, for the reader to focus once', () => {
    expect(noteHref(id, other)).toBe(`#/papers/${id}?note=${other}`)
    expect(parseRoute(noteHref(id, other))).toEqual({
      name: 'reader',
      paperId: id,
      tab: 'notes',
      target: { kind: 'note', id: other },
    })
  })

  it('ignores a target with a malformed id, or a chunk without a page', () => {
    const reader = { name: 'reader', paperId: id, tab: 'notes', target: null }
    expect(parseRoute(`#/papers/${id}?note=not-an-id`)).toEqual(reader)
    expect(parseRoute(`#/papers/${id}?chunk=${other}`)).toEqual(reader)
    expect(parseRoute(`#/papers/${id}?chunk=${other}&page=0`)).toEqual(reader)
  })

  it('opens a workspace on its Papers tab by default, and keeps another tab in the hash', () => {
    expect(workspaceHref(id)).toBe(`#/workspaces/${id}`)
    expect(parseRoute(workspaceHref(id))).toEqual({ name: 'workspace', workspaceId: id, tab: 'papers' })
    expect(workspaceHref(id, 'chat')).toBe(`#/workspaces/${id}?tab=chat`)
    expect(parseRoute(workspaceHref(id, 'notes'))).toEqual({ name: 'workspace', workspaceId: id, tab: 'notes' })
    expect(parseRoute(`#/workspaces/${id}?tab=graph`)).toEqual({ name: 'workspace', workspaceId: id, tab: 'papers' })
  })

  it('falls back to the library for anything else', () => {
    expect(parseRoute('')).toEqual({ name: 'library' })
    expect(parseRoute('#/')).toEqual({ name: 'library' })
    expect(parseRoute('#/papers/not-an-id')).toEqual({ name: 'library' })
    expect(parseRoute('#/workspaces/not-an-id')).toEqual({ name: 'library' })
  })
})
