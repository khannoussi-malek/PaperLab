import { describe, expect, it } from 'vitest'
import type { Note, Paper } from '@/api/client'
import { countsLine, notesByPaper } from './workspaceMeta'

const paper = (id: string, title: string) => ({ id, title }) as Paper
const note = (id: string, ...paperIds: string[]) =>
  ({ id, anchors: paperIds.map((paper_id) => ({ paper_id, page: 1, bbox: [], quoted_text: id })) }) as unknown as Note

describe('countsLine', () => {
  it('counts papers and notes, singular or plural', () => {
    expect(countsLine(1, 1)).toBe('1 paper · 1 note')
    expect(countsLine(6, 0)).toBe('6 papers · 0 notes')
  })

  it('says how many papers are not indexed yet, when any are', () => {
    expect(countsLine(6, 31, 1)).toBe('6 papers (1 not indexed) · 31 notes')
  })
})

describe('notesByPaper', () => {
  const dpr = paper('p-dpr', 'Dense Passage Retrieval')
  const bert = paper('p-bert', 'BERT')

  it('groups notes under their paper, papers in title order, notes in the order the API sent them', () => {
    const notes = [note('n1', 'p-dpr'), note('n2', 'p-bert'), note('n3', 'p-dpr')]
    expect(notesByPaper(notes, [dpr, bert])).toEqual([
      { paper: bert, notes: [notes[1]] },
      { paper: dpr, notes: [notes[0], notes[2]] },
    ])
  })

  it('shows a note anchored on two workspace papers once, under the anchor whose paper sorts first', () => {
    const both = note('n1', 'p-elsewhere', 'p-dpr', 'p-bert')
    expect(notesByPaper([both], [dpr, bert])).toEqual([{ paper: bert, notes: [both] }])
  })

  it('leaves out notes with no anchor on a workspace paper, and papers with no notes', () => {
    expect(notesByPaper([note('n1', 'p-elsewhere'), note('n2')], [dpr, bert])).toEqual([])
  })
})
