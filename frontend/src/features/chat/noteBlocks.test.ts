import { describe, expect, it } from 'vitest'
import type { ChatSource } from '@/api/client'
import cases from './noteBlocks.cases.json'
import {
  ALREADY_SAVED,
  partSelection,
  promoteInPart,
  savedNoteHref,
  splitNoteBlocks,
  suggestionError,
  type NotePart,
} from './noteBlocks'

const texts = (content: string, parts: NotePart[], kind: NotePart['kind']) =>
  parts.filter((part) => part.kind === kind).map((part) => content.slice(part.start, part.end))

// The backend's notes.note_blocks is tested on the same cases (backend/tests/test_suggestions.py).
describe('splitNoteBlocks', () => {
  it.each(cases)('reads "$name" as the backend does', ({ content, blocks }) => {
    const parts = splitNoteBlocks(content)
    expect(texts(content, parts, 'note')).toEqual(blocks)
    expect(parts.flatMap((part) => (part.kind === 'note' ? [part.index] : []))).toEqual(blocks.map((_, i) => i))
  })

  it.each(cases)('tiles "$name" exactly, so the answer’s text stays whole', ({ content }) => {
    const parts = splitNoteBlocks(content)
    expect(parts.map((part) => content.slice(part.start, part.end)).join('')).toBe(content)
    expect(parts.every((part, i) => part.start === (i === 0 ? 0 : parts[i - 1].end))).toBe(true)
  })

  it('shows a block while it streams in, before its closing line', () => {
    const streaming = 'Here are notes.\n:::note\nFirst idea [C'
    expect(texts(streaming, splitNoteBlocks(streaming), 'note')).toEqual(['First idea [C'])
    expect(texts(streaming, splitNoteBlocks(streaming), 'prose')).toEqual(['Here are notes.\n'])
  })

  it('gives prose, notes and the marker lines between them their offsets', () => {
    expect(splitNoteBlocks('Two notes.\n:::note\nA [C1].\n:::\nAfter.')).toEqual([
      { kind: 'prose', start: 0, end: 11 },
      { kind: 'marker', start: 11, end: 19 },
      { kind: 'note', index: 0, start: 19, end: 26 },
      { kind: 'marker', start: 26, end: 31 },
      { kind: 'prose', start: 31, end: 37 },
    ])
    expect(splitNoteBlocks('No blocks [C1].')).toEqual([{ kind: 'prose', start: 0, end: 15 }])
    expect(splitNoteBlocks('')).toEqual([])
  })
})

describe('Save as note in an answer with suggested notes', () => {
  const answer =
    'Here are notes [C2].\n:::note\nSelf-attention relates positions [C1].\n:::\n:::note\nKeep one idea.\n:::\n' +
    'All from the method [C1].'
  const sources = [
    { label: 'C1', chunk_id: 'chunk-1' },
    { label: 'C2', chunk_id: 'chunk-2' },
  ] as ChatSource[]
  const at = (text: string) => answer.indexOf(text)

  it('stays in the part it starts in: prose dragged into a card keeps only the prose', () => {
    expect(promoteInPart(answer, sources, 0, at('relates'))).toEqual({ body: 'Here are notes [C2].', chunkIds: ['chunk-2'] })
  })

  it('maps a selection inside a card to the card’s text and the passages it cites', () => {
    expect(promoteInPart(answer, sources, at('Self'), at('[C1].') + 5)).toEqual({
      body: 'Self-attention relates positions [C1].',
      chunkIds: ['chunk-1'],
    })
  })

  it('never borrows a passage from outside a card that cites none', () => {
    expect(promoteInPart(answer, sources, at('Keep'), at('idea.') + 5)).toEqual({ body: 'Keep one idea.', chunkIds: [] })
  })

  it('starts at the next part when the selection starts on a marker line, in either direction', () => {
    const fromMarker = partSelection(splitNoteBlocks(answer), at(':::note'), at('Self') + 4)
    expect(fromMarker && answer.slice(fromMarker.start, fromMarker.end)).toBe('Self')
    expect(promoteInPart(answer, sources, at('method') + 6, at('All'))).toEqual({
      body: 'All from the method',
      chunkIds: ['chunk-1'],
    })
  })

  it('reads an answer without blocks exactly as promote.ts does', () => {
    expect(promoteInPart('One [C1].\n\nTwo [C2].', sources, 11, 14)).toEqual({ body: 'Two', chunkIds: ['chunk-2'] })
  })
})

describe('a saved suggestion', () => {
  it('opens the chat’s paper while the note is still on it, else its first paper, else No paper', () => {
    const saved = { note_id: 'n1', paper_ids: ['p-a', 'p-b'] }
    expect(savedNoteHref(saved, 'p-b')).toBe('#/papers/p-b?note=n1')
    expect(savedNoteHref(saved, 'p-other')).toBe('#/papers/p-a?note=n1')
    expect(savedNoteHref(saved, null)).toBe('#/papers/p-a?note=n1')
    expect(savedNoteHref({ note_id: 'n1', paper_ids: [] }, 'p-b')).toBe('#/notes?paper=none')
  })

  it('says nothing for already_saved: the refetched history shows it Saved', () => {
    expect(suggestionError(new Error(ALREADY_SAVED))).toBeNull()
  })

  it('puts a refusal in words, and shows any other message as the API sent it', () => {
    expect(suggestionError(new Error('empty_body'))).toBe('This suggested note is empty, so there is nothing to save.')
    expect(suggestionError(new Error('no_such_block'))).toBe('This suggested note is no longer in the saved answer.')
    expect(suggestionError(new Error('answer_not_found'))).toBe("This answer was deleted, so its notes can't be saved.")
    expect(suggestionError(new TypeError('Failed to fetch'))).toBe("Couldn't save the note. Try again.")
    const stale = 'a cited chunk no longer exists; the paper was re-ingested, so ask again'
    expect(suggestionError(new Error(stale))).toBe(stale)
  })
})
