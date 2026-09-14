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

  it('groups notes under their paper, in the order the API sent them (already sorted by title, then paper)', () => {
    // A real response from the API is already sorted this way (core/workspaces.py); the client trusts that order
    // instead of re-deriving it, so the input here is BERT's note first, matching "BERT" < "Dense Passage Retrieval".
    const notes = [note('n1', 'p-bert'), note('n2', 'p-dpr'), note('n3', 'p-dpr')]
    expect(notesByPaper(notes, [dpr, bert])).toEqual([
      { paper: bert, notes: [notes[0]] },
      { paper: dpr, notes: [notes[1], notes[2]] },
    ])
  })

  it('shows a note anchored on two workspace papers once, under the anchor whose paper sorts first', () => {
    const both = note('n1', 'p-elsewhere', 'p-dpr', 'p-bert')
    expect(notesByPaper([both], [dpr, bert])).toEqual([{ paper: bert, notes: [both] }])
  })

  it('breaks a title tie with plain comparison, not localeCompare (which disagrees with the backend on case)', () => {
    // localeCompare sorts "attention…" before "BERT" (case-insensitive-ish collation); the backend's Python
    // comparison, which plain `<`/`>` matches, sorts "BERT" first (uppercase code points sort below lowercase).
    const attention = paper('p-attn', 'attention is all you need')
    const bertPaper = paper('p-bert2', 'BERT')
    const both = note('n1', 'p-attn', 'p-bert2')
    expect(notesByPaper([both], [attention, bertPaper])).toEqual([{ paper: bertPaper, notes: [both] }])
  })

  it('breaks an identical-title tie by paper id, plain comparison, not anchor order', () => {
    const zzz = paper('p-zzz', 'Same Title')
    const aaa = paper('p-aaa', 'Same Title')
    // Anchors list p-zzz first; the correct pick is p-aaa, since "p-aaa" < "p-zzz".
    const both = note('n1', 'p-zzz', 'p-aaa')
    expect(notesByPaper([both], [zzz, aaa])).toEqual([{ paper: aaa, notes: [both] }])
  })

  it('leaves out notes with no anchor on a workspace paper, and papers with no notes', () => {
    expect(notesByPaper([note('n1', 'p-elsewhere'), note('n2')], [dpr, bert])).toEqual([])
  })
})
