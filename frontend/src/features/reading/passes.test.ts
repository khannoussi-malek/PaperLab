import { describe, expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { emptyListText, matchesReading, nextPass, PASSES, readingChip, type Triage } from './passes'

describe('PASSES', () => {
  it('has three passes, with Keshav 2007’s headings', () => {
    expect(PASSES.map((pass) => pass.heading)).toEqual(['Pass 1 · 5–10 minutes', 'Pass 2 · about an hour', 'Pass 3 · 1–5 hours'])
  })
})

describe('nextPass', () => {
  it('gives the next pass for 0–2, and none once every pass is finished', () => {
    expect([0, 1, 2].map(nextPass)).toEqual([PASSES[0], PASSES[1], PASSES[2]])
    expect(nextPass(3)).toBeNull()
  })
})

describe('readingChip', () => {
  it('is null at the normal state, and otherwise names the level, the decision, or both', () => {
    expect(readingChip(0, null)).toBeNull()
    expect(readingChip(0, 'later')).toBe('Later')
    expect(readingChip(0, 'drop')).toBe('Dropped')
    expect(readingChip(2, null)).toBe('Pass 2')
    expect(readingChip(2, 'later')).toBe('Pass 2 · Later')
  })
})

describe('matchesReading', () => {
  const paper = (reading_pass: number, triage: Triage | null) => ({ reading_pass, triage }) as Pick<Paper, 'reading_pass' | 'triage'>

  it('is true for every paper at all, and matches unread/keep/later/drop otherwise', () => {
    expect(matchesReading(paper(2, 'keep'), 'all')).toBe(true)
    expect(matchesReading(paper(0, null), 'unread')).toBe(true)
    expect(matchesReading(paper(0, 'drop'), 'unread')).toBe(false) // Q1 (b): a dropped paper isn't "unread" any more
    expect(matchesReading(paper(2, null), 'unread')).toBe(false)
    expect(matchesReading(paper(1, 'later'), 'later')).toBe(true)
    expect(matchesReading(paper(1, 'keep'), 'later')).toBe(false)
  })
})

describe('emptyListText', () => {
  it('names the query, the filter, or both — never a blank page', () => {
    expect(emptyListText('', 'all')).toBe('No unread papers.')
    expect(emptyListText('', 'unread')).toBe('No unread papers.')
    expect(emptyListText('', 'keep')).toBe('No papers marked Keep.')
    expect(emptyListText('', 'later')).toBe('No papers marked Later.')
    expect(emptyListText('', 'drop')).toBe('No dropped papers.')
    expect(emptyListText('turing', 'all')).toBe('No papers match “turing”')
    expect(emptyListText('turing', 'keep')).toBe('No papers match “turing” in Keep')
  })
})
