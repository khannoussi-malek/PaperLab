import { describe, expect, it } from 'vitest'
import { sameTarget, type HoverTarget } from './useHoverCard'

describe('sameTarget', () => {
  const citation: HoverTarget = { kind: 'citation', page: 1, citationId: '38R' }
  const notes: HoverTarget = { kind: 'notes', page: 1, noteIds: ['a', 'b'] }

  it('is the same kind, page and ids', () => {
    expect(sameTarget(citation, { kind: 'citation', page: 1, citationId: '38R' })).toBe(true)
    expect(sameTarget(notes, { kind: 'notes', page: 1, noteIds: ['a', 'b'], editNoteId: 'a' })).toBe(true)
  })

  it('differs by kind, page or id, and from no card at all', () => {
    expect(sameTarget(citation, { kind: 'citation', page: 1, citationId: '39R' })).toBe(false)
    expect(sameTarget(citation, { kind: 'citation', page: 2, citationId: '38R' })).toBe(false)
    expect(sameTarget(notes, { kind: 'notes', page: 1, noteIds: ['a'] })).toBe(false)
    expect(sameTarget(notes, { kind: 'citation', page: 1, citationId: 'a,b' })).toBe(false)
    expect(sameTarget(null, citation)).toBe(false)
  })
})
