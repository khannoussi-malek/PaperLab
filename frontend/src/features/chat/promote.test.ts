import { describe, expect, it } from 'vitest'
import type { ChatSource } from '@/api/client'
import { promoteErrorMessage, promoteSelection } from './promote'

const source = (label: string): ChatSource => ({
  label,
  chunk_id: `chunk-${label}`,
  paper_id: 'paper-1',
  page: 1,
  section: null,
  bbox: [],
})
const SOURCES = [source('C1'), source('C2'), source('C3')]
const ANSWER =
  'Highlights anchor notes [C1]. They keep the page [C3].\n\nA second paragraph cites [C2].\n\nNo citations here.'

/** Offsets of `fragment` in `content`, as a selection over exactly that text would give. */
const over = (fragment: string, content = ANSWER): [number, number] => {
  const start = content.indexOf(fragment)
  return [start, start + fragment.length]
}

describe('promoteSelection', () => {
  it('anchors on the chunks cited inside the selection, in order', () => {
    expect(promoteSelection(ANSWER, SOURCES, ...over('anchor notes [C1]. They keep the page [C3]'))).toEqual({
      body: 'anchor notes [C1]. They keep the page [C3]',
      chunkIds: ['chunk-C1', 'chunk-C3'],
    })
  })

  it('counts a half-selected marker and saves it whole, so the body stays verbatim', () => {
    expect(promoteSelection(ANSWER, SOURCES, ...over('notes [C'))).toEqual({
      body: 'notes [C1]',
      chunkIds: ['chunk-C1'],
    })
  })

  it('falls back to the markers of the paragraph the selection starts in', () => {
    expect(promoteSelection(ANSWER, SOURCES, ...over('A second paragraph'))).toEqual({
      body: 'A second paragraph',
      chunkIds: ['chunk-C2'],
    })
  })

  it('has nothing to anchor on when neither the selection nor its paragraph cites a source', () => {
    expect(promoteSelection(ANSWER, SOURCES, ...over('No citations'))).toEqual({
      body: 'No citations',
      chunkIds: [],
    })
  })

  it('ignores unknown markers and chunks a re-ingest removed', () => {
    const content = 'Old claim [C2] and [C9].'
    expect(promoteSelection(content, [source('C1'), null], 0, content.length)).toEqual({
      body: content,
      chunkIds: [],
    })
  })

  it('reads a backwards selection like a forwards one, trims it, and ignores a blank one', () => {
    const [start, end] = over('\nA second paragraph ')
    expect(promoteSelection(ANSWER, SOURCES, end, start)).toEqual({ body: 'A second paragraph', chunkIds: ['chunk-C2'] })
    expect(promoteSelection(ANSWER, SOURCES, ...over('\n\n'))).toBeNull()
  })

  it('has nothing to anchor on when the selection cites only notes, even with passages in its paragraph', () => {
    const content = 'Both papers describe it [C1][C2], as your note says [N1].'
    expect(promoteSelection(content, SOURCES, ...over('as your note says [N1]', content))).toEqual({
      body: 'as your note says [N1]',
      chunkIds: [],
    })
  })

  it('anchors a selection citing passages and a note on the passages only', () => {
    const content = 'Both papers describe it [C1][C2], as your note says [N1].'
    expect(promoteSelection(content, SOURCES, 0, content.length)).toEqual({
      body: content,
      chunkIds: ['chunk-C1', 'chunk-C2'],
    })
  })

  it('computes the paragraph fallback from the trimmed body, not a start sitting on the break itself', () => {
    // The selection starts on the leading "\n" of the "\n\n" before paragraph 2, not inside paragraph 2's text.
    // The body still trims down to paragraph 2, so its anchors must be paragraph 2's markers, not paragraph 1's.
    const breakStart = ANSWER.indexOf('\n\n')
    const [, end] = over('A second paragraph')
    expect(promoteSelection(ANSWER, SOURCES, breakStart, end)).toEqual({
      body: 'A second paragraph',
      chunkIds: ['chunk-C2'],
    })
  })
})

describe('promoteErrorMessage', () => {
  it("words the API's stale-selection code, and shows any other refusal's own text", () => {
    expect(promoteErrorMessage(new Error('body_not_in_output'))).toBe("This selection doesn't match the saved answer. Select the text again.")
    expect(promoteErrorMessage(new Error('Check these fields: body.'))).toBe('Check these fields: body.')
  })

  it('says to try again when the request never got an answer', () => {
    expect(promoteErrorMessage(new TypeError('Failed to fetch'))).toBe("Couldn't save the note. Try again.")
    expect(promoteErrorMessage('boom')).toBe("Couldn't save the note. Try again.")
    expect(promoteErrorMessage(new Error(''))).toBe("Couldn't save the note. Try again.")
  })
})
