import { describe, expect, it } from 'vitest'
import { clientPointToPdf, notesAt, rectContains, type NoteRect } from './hitTest'

const highlights: NoteRect[] = [
  { noteId: 'a', rect: [72, 400, 290, 410] },
  { noteId: 'a', rect: [72, 412, 200, 422] }, // second line of the same note
  { noteId: 'b', rect: [150, 405, 250, 415] }, // overlaps note a
  { noteId: null, rect: [300, 400, 400, 410] }, // the unsaved draft
]

describe('notesAt', () => {
  it('finds the note whose rect contains the point', () => {
    expect(notesAt(highlights, [100, 418])).toEqual(['a'])
  })

  it('returns nothing outside every rect', () => {
    expect(notesAt(highlights, [50, 50])).toEqual([])
  })

  it('ignores the draft highlight', () => {
    expect(notesAt(highlights, [350, 405])).toEqual([])
  })

  it('returns every overlapping note once, in highlight order', () => {
    expect(notesAt(highlights, [160, 408])).toEqual(['a', 'b'])
  })
})

describe('clientPointToPdf', () => {
  it('converts a viewport pointer position into PDF points on the page', () => {
    expect(clientPointToPdf({ x: 158, y: 1600 }, { left: 50, top: 1000 }, 1.5)).toEqual([72, 400])
  })
})

describe('rectContains', () => {
  it('includes the edges and excludes points outside', () => {
    expect(rectContains([10, 10, 20, 20], [10, 20])).toBe(true)
    expect(rectContains([10, 10, 20, 20], [21, 15])).toBe(false)
  })
})
