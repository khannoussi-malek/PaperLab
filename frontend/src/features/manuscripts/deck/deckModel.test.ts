import { describe, expect, it } from 'vitest'
import type { CitablePaper, Note } from '@/api/client'
import { bookItems, cardTransform, citedKeys, deckOrder, insertText, turnDirection, windowAround } from './deckModel'
import { latexEscape } from './latex'

const paper = (id: string, title: string): CitablePaper => ({
  paper_id: id, key: id, pinned: false, title, first_author: null, year: null, has_pdf: false, notes: 0, highlights: 0, ai_notes: 0,
})
const anchor = (paper_id: string, page: number, quoted_text = 'q') => ({ paper_id, page, bbox: [[0, 0, 1, 1]] as [number, number, number, number][], quoted_text })
const note = (id: string, o: Partial<Note>): Note =>
  ({ id, body: 'b', provenance: 'human', anchors: [], paper_ids: [], ...o }) as unknown as Note

describe('citedKeys', () => {
  it('reads every command form and skips comments', () => {
    const src =
      '\\cite{a} \\citep[see][p. 3]{b, c} \\citet*{d}\\citealp{e}\\citeauthor{f}\\citeyear{g}\\nocite{h,a}\n' +
      '% \\cite{hidden}\n' +
      'text 50\\% \\cite{i} % \\cite{gone}\n'
    expect([...citedKeys([src])]).toEqual([...'abcdefghi'])
  })
  it('reads natbib and biblatex commands', () => {
    const src =
      '\\citealt{a} \\citenum{b} \\citeyearpar[p.~2]{c} \\Citet{d} \\Citep*[see][]{e} \\Citealp{f}\n' +
      '\\parencite{g} \\textcite[ch.~3]{h} \\autocite{i} \\Parencite{j} \\footcite{k} \\citeauthor*{l}\n' +
      '% \\textcite{hidden}\n' +
      '\\recite{m} \\excite{n}\n'
    expect([...citedKeys([src])]).toEqual([...'abcdefghijklmn'])
  })
  it('joins several sources', () => {
    expect([...citedKeys(['\\cite{a}', '\\cite{b,a}'])]).toEqual(['a', 'b'])
  })
})

describe('deckOrder', () => {
  const ps = [paper('p1', 'Zeta'), paper('p2', 'Alpha'), paper('p3', 'Mid'), paper('p4', 'Beta'), paper('p5', 'Gamma')]
  it('section, then elsewhere, then ranked, then title', () => {
    const out = deckOrder(ps, new Set(['p5']), new Set(['p1']), ['p3'])
    expect(out.map((p) => p.paper_id)).toEqual(['p5', 'p1', 'p3', 'p2', 'p4'])
  })
  it('does not mutate its input', () => {
    const copy = [...ps]
    deckOrder(ps, new Set(), new Set(), [])
    expect(ps).toEqual(copy)
  })
})

describe('bookItems', () => {
  it('splits notes into highlights, notes and ai items in page order', () => {
    const notes = [
      note('n1', { anchors: [anchor('p', 5, 'five'), anchor('x', 1), anchor('p', 2, 'two')], paper_ids: ['p', 'x'] }),
      note('n2', { body: 'plain', paper_ids: ['p'] }),
      note('n3', { body: 'ai', provenance: 'llm', anchors: [anchor('p', 3)], paper_ids: ['p'] }),
      note('n4', { body: 'ai2', provenance: 'llm_edited', paper_ids: ['p'] }),
      note('n5', { paper_ids: ['other'] }),
    ]
    const items = bookItems(notes, 'p')
    expect(items.map((i) => [i.kind, i.page, i.text, i.noteId])).toEqual([
      ['highlight', 2, 'two', 'n1'],
      ['ai', 3, 'ai', 'n3'],
      ['highlight', 5, 'five', 'n1'],
      ['note', null, 'plain', 'n2'],
      ['ai', null, 'ai2', 'n4'],
    ])
    expect(new Set(items.map((i) => i.id)).size).toBe(items.length)
  })
  it('is empty for a paper with no notes', () => expect(bookItems([], 'p')).toEqual([]))
})

describe('insertText', () => {
  const item = (kind: 'highlight' | 'note' | 'ai', text: string, page: number | null = null) => ({ id: 'i', kind, page, text, noteId: 'n' })
  it('paper, highlight, note', () => {
    expect(insertText(null, 'k')).toBe('\\citep{k}')
    expect(insertText(item('highlight', '50% of A_B & {x}', 4), 'k')).toBe("``50\\% of A\\_B \\& \\{x\\}'' \\citep[p.~4]{k}")
    expect(insertText(item('note', 'a # b'), 'k')).toBe('a \\# b \\citep{k}')
  })
  it('comments an AI note line by line, nothing else', () => {
    expect(insertText(item('ai', 'one \\input{x}\n\ntwo'), 'k')).toBe(
      '% AI note (not your text): one \\input{x}\n% AI note (not your text): \n% AI note (not your text): two',
    )
  })
})

describe('latexEscape', () => {
  it('escapes every special', () => {
    expect(latexEscape('\\ # $ % & _ { } ~ ^')).toBe(
      '\\textbackslash{} \\# \\$ \\% \\& \\_ \\{ \\} \\textasciitilde{} \\textasciicircum{}',
    )
  })
})

describe('motion helpers', () => {
  it('turnDirection', () => {
    expect(turnDirection(1, 3)).toBe('fwd')
    expect(turnDirection(3, 1)).toBe('bwd')
  })
  it('cardTransform', () => {
    expect(cardTransform(0)).toEqual({ transform: 'translateX(0px) translateZ(0px) rotateY(0deg)', zIndex: 10, opacity: 1 })
    expect(cardTransform(-1).transform).toBe('translateX(-95px) translateZ(-120px) rotateY(38deg)')
    expect(cardTransform(3).opacity).toBe(0)
  })
  it('windowAround clips at the ends', () => {
    expect(windowAround(10, 0)).toEqual([0, 1, 2, 3])
    expect(windowAround(10, 9)).toEqual([6, 7, 8, 9])
    expect(windowAround(10, 5, 1)).toEqual([4, 5, 6])
    expect(windowAround(0, 0)).toEqual([])
  })
})
