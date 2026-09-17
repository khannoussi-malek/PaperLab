import { describe, expect, it } from 'vitest'
import type { Reference } from '@/api/client'
import { cocitationBadge, rowAction, summaryLine } from './referencesMeta'

describe('summaryLine', () => {
  it('joins both halves when both counts are positive', () => {
    expect(summaryLine({ cited_by_3plus: 5, with_pdf: 3 }, 'cites')).toBe('5 cited by 3+ of your papers, 3 have PDFs')
  })

  it('says the citing works cite 3+ of your papers, since that is what their count means', () => {
    expect(summaryLine({ cited_by_3plus: 5, with_pdf: 3 }, 'cited_by')).toBe('5 cite 3+ of your papers, 3 have PDFs')
  })

  it('drops the cited-by half when its count is zero', () => {
    expect(summaryLine({ cited_by_3plus: 0, with_pdf: 3 }, 'cites')).toBe('3 have PDFs')
  })

  it('drops the PDF half when its count is zero', () => {
    expect(summaryLine({ cited_by_3plus: 5, with_pdf: 0 }, 'cites')).toBe('5 cited by 3+ of your papers')
  })

  it('is null when both counts are zero', () => {
    expect(summaryLine({ cited_by_3plus: 0, with_pdf: 0 }, 'cited_by')).toBeNull()
  })
})

describe('cocitationBadge', () => {
  it('is null at 0 or 1 (only the paper being read cites it)', () => {
    expect(cocitationBadge(0, 'cites')).toBeNull()
    expect(cocitationBadge(1, 'cited_by')).toBeNull()
  })

  it('names the count once 2 or more library papers cite it', () => {
    expect(cocitationBadge(2, 'cites')).toBe('Cited by 2 of your papers')
    expect(cocitationBadge(7, 'cites')).toBe('Cited by 7 of your papers')
  })

  it('names the library papers a citing work cites', () => {
    expect(cocitationBadge(3, 'cited_by')).toBe('Cites 3 of your papers')
  })
})

describe('rowAction', () => {
  const reference = (fields: Partial<Reference>) => ({ has_pdf: false, paper_id: null, ...fields })

  it('is in-library whenever paper_id is set, even with a PDF', () => {
    expect(rowAction(reference({ paper_id: 'p1', has_pdf: true }))).toBe('in-library')
  })

  it('is import when not in the library but a free PDF is listed', () => {
    expect(rowAction(reference({ has_pdf: true }))).toBe('import')
  })

  it('is null when not in the library and no free PDF is listed', () => {
    expect(rowAction(reference({}))).toBeNull()
  })
})
