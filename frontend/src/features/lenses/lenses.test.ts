import { describe, expect, it } from 'vitest'
import type { Lens, Section } from '@/api/client'
import { NO_PDF_LENS_TEXT, briefProblem, emptyLensText, fadeRects, lensNotice, lensRuns, lensSections, stepRun } from './lenses'

type Rect = [number, number, number, number]
const chunk = (id: string, page: number, ...bbox: Rect[]) => ({ id, page, bbox })
const lens = (fields: Partial<Lens>): Lens => ({
  id: 'key_ideas',
  label: 'Key ideas',
  chunk_ids: ['a'],
  positional_fallback: false,
  missing_roles: [],
  ...fields,
})
const section = (title: string, chunkIds: string[]): Section => ({
  title,
  role: 'other',
  source: 'none',
  chunk_ids: chunkIds,
  first_chunk_id: chunkIds[0],
  page: 1,
  preview: '',
})

describe('fadeRects', () => {
  it('fades every rect of the chunks outside the lens, and none inside it', () => {
    const page = [chunk('a', 2, [72, 110, 300, 140]), chunk('b', 2, [72, 150, 300, 170], [320, 150, 540, 170])]
    expect(fadeRects(page, new Set(['a']))).toEqual([
      [72, 150, 300, 170],
      [320, 150, 540, 170],
    ])
  })

  it('fades nothing on a page the lens covers', () => {
    expect(fadeRects([chunk('a', 1, [0, 0, 1, 1])], new Set(['a']))).toEqual([])
  })

  it('fades the whole of a page the lens never reaches', () => {
    expect(fadeRects([chunk('a', 1, [0, 0, 1, 1]), chunk('b', 1, [0, 2, 1, 3])], new Set(['z']))).toEqual([
      [0, 0, 1, 1],
      [0, 2, 1, 3],
    ])
  })
})

describe('lensRuns', () => {
  const chunks = ['a', 'b', 'c', 'd', 'e'].map((id, i) => chunk(id, i + 1, [0, 0, 1, 1]))

  it('makes one run of consecutive lens chunks and starts another after a gap', () => {
    expect(lensRuns(chunks, new Set(['a', 'b', 'd'])).map((c) => c.id)).toEqual(['a', 'd'])
  })

  it('gives a lens at the end of the paper one run', () => {
    expect(lensRuns(chunks, new Set(['c', 'd', 'e'])).map((c) => c.id)).toEqual(['c'])
  })

  it('gives an empty lens no runs', () => {
    expect(lensRuns(chunks, new Set())).toEqual([])
  })
})

describe('stepRun', () => {
  it('moves one run at a time and stops at either end', () => {
    expect([stepRun(0, 3, 1), stepRun(2, 3, 1), stepRun(0, 3, -1), stepRun(1, 3, -1)]).toEqual([1, 2, 0, 0])
  })
})

describe('lensNotice', () => {
  it('says nothing for Full paper or for a lens that found its sections', () => {
    expect(lensNotice(lens({ id: 'full', label: 'Full paper' }))).toBeNull()
    expect(lensNotice(lens({ missing_roles: ['conclusion'] }))).toBeNull()
  })

  it('names the lens in the empty state', () => {
    expect(lensNotice(lens({ id: 'related', label: 'Related work', chunk_ids: [] }))).toEqual({
      kind: 'empty',
      text: "This paper has no sections for Related work. Switch to Full paper to fix a section's role.",
    })
  })

  it('says when Key ideas shows the start and end of the paper', () => {
    expect(lensNotice(lens({ positional_fallback: true }))).toEqual({
      kind: 'fallback',
      text: 'No Introduction or Conclusion headings found. Showing the start and end of the paper.',
    })
  })

  it('says when Critical check has no limitations section', () => {
    const critical = lens({ id: 'critical', label: 'Critical check', missing_roles: ['results', 'limitations'] })
    expect(lensNotice(critical)).toEqual({ kind: 'missing', text: 'No limitations section found in this paper.' })
  })

  it('gives an empty Critical check the empty state, not the limitations line', () => {
    const critical = lens({ id: 'critical', label: 'Critical check', chunk_ids: [], missing_roles: ['limitations'] })
    expect(lensNotice(critical)?.kind).toBe('empty')
  })
})

describe('lensNotice without a PDF', () => {
  it("never shows the Key ideas positional-fallback banner for a paper without a PDF (R1)", () => {
    // The paper's only chunk is its ABSTRACT_PAGE abstract; even a lens that claims a fallback says one thing only.
    const notice = lensNotice(lens({ positional_fallback: true }), false)

    expect(notice?.kind).not.toBe('fallback')
    expect(notice).toEqual({ kind: 'no_pdf', text: "Lenses read a paper's sections. Attach its PDF to use them." })
    expect(notice?.text).toBe(NO_PDF_LENS_TEXT)
  })

  it('says it for Full paper and for an empty lens too, and still says nothing else for a paper with a PDF', () => {
    expect(lensNotice(lens({ id: 'full', label: 'Full paper' }), false)?.kind).toBe('no_pdf')
    expect(lensNotice(lens({ chunk_ids: [] }), false)?.kind).toBe('no_pdf')
    expect(lensNotice(lens({ id: 'full', label: 'Full paper' }), true)).toBeNull()
  })
})

describe('lensSections', () => {
  const sections = [section('1 Introduction', ['a', 'b']), section('2 Method', ['c']), section('3 Results', ['d'])]

  it('lists every section for Full paper', () => {
    expect(lensSections(sections, lens({ id: 'full', chunk_ids: ['a', 'b', 'c', 'd'] }))).toEqual(sections)
  })

  it('lists the sections with a chunk in the lens, including one it only partly covers', () => {
    expect(lensSections(sections, lens({ chunk_ids: ['b', 'd'] })).map((s) => s.title)).toEqual([
      '1 Introduction',
      '3 Results',
    ])
  })
})

describe('briefProblem', () => {
  it('words an empty lens as the Lens tab does', () => {
    expect(briefProblem(409, 'lens_empty', 'Related work')).toEqual({
      message: emptyLensText('Related work'),
      retryable: false,
      reindex: false,
    })
  })

  it('words a paper without a PDF as the Lens tab does', () => {
    expect(briefProblem(409, 'needs_full_text', 'Key ideas')).toEqual({
      message: NO_PDF_LENS_TEXT,
      retryable: false,
      reindex: false,
    })
  })

  it('words the other refusals as chat does', () => {
    expect(briefProblem(409, 'paper_not_ready', 'Key ideas').message).toBe(
      'This paper is still being processed. Ask again once it is ready.',
    )
    expect(briefProblem(500, 'boom', 'Key ideas')).toEqual({ message: 'boom', retryable: true, reindex: false })
  })
})
