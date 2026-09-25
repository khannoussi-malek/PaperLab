import { describe, expect, it } from 'vitest'
import type { Note } from '@/api/client'
import { unlinkWarnings } from './notePapers'

const anchor = (paper_id: string, page: number) => ({ paper_id, page, bbox: [], quoted_text: 'q' })
const note = { anchors: [anchor('p-bert', 4), anchor('p-bert', 2), anchor('p-dpr', 7)] } as unknown as Note
const papers = [
  { id: 'p-bert', title: 'BERT' },
  { id: 'p-dpr', title: 'Dense Passage Retrieval' },
  { id: 'p-new', title: 'New' },
]

describe('unlinkWarnings', () => {
  it('warns once per unticked paper the note has a highlight on, at its first page there', () => {
    expect(unlinkWarnings(note, papers, ['p-dpr'])).toEqual(['Its highlight on p. 2 in BERT will be removed.'])
    expect(unlinkWarnings(note, papers, [])).toEqual([
      'Its highlight on p. 2 in BERT will be removed.',
      'Its highlight on p. 7 in Dense Passage Retrieval will be removed.',
    ])
  })

  it('says nothing while every highlighted paper stays ticked, or for a note with no highlight', () => {
    expect(unlinkWarnings(note, papers, ['p-bert', 'p-dpr', 'p-new'])).toEqual([])
    expect(unlinkWarnings({ anchors: [] }, papers, [])).toEqual([])
  })
})
