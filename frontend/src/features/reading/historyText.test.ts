import { describe, expect, it } from 'vitest'
import type { TriageEvent } from '@/api/client'
import { describeEvent } from './historyText'

const at = (h: number, m: number) => new Date(2026, 9, 29, h, m).toISOString()
const event = (over: Partial<TriageEvent>): TriageEvent => ({
  id: 'e1', paper_id: 'p1', session_id: null, client_id: null, source: 'desk', pile: null,
  before_triage: null, after_triage: null, before_pass: 0, after_pass: 0, reason: null, note: null, fivecs: null,
  pdf_opened: false, pdf_ms: null, card_ms: null, undone_event_id: null, created_at: at(14, 2), ...over,
})
const line = (e: TriageEvent) => {
  const r = describeEvent(e)
  return [r.when, r.what, r.why, r.where].filter(Boolean).join(' · ')
}

describe('describeEvent', () => {
  it('reads a desk drop with its reason', () => {
    expect(line(event({ pile: 'not_relevant', reason: 'off_topic', after_triage: 'drop' }))).toBe(
      '29 Oct, 14:02 · Dropped · off topic · from the desk'
    )
  })
  it.each([
    ['read_closely', 'Read closely'],
    ['skim', 'Skim'],
    ['later', 'Later'],
    ['skip', 'Skipped'],
  ])('names the %s pile in the desk words', (pile, word) => {
    expect(describeEvent(event({ pile })).what).toBe(word)
  })
  it('maps reason keys to words', () => {
    expect(describeEvent(event({ pile: 'later', reason: 'needs_background' })).why).toBe('needs background first')
    expect(describeEvent(event({ pile: 'later', reason: 'maybe_relevant_later' })).why).toBe('maybe relevant later')
  })
  it('reads a library change from before and after, with no reason', () => {
    const e = event({ source: 'library', before_pass: 1, after_pass: 1, before_triage: null, after_triage: 'later', created_at: at(14, 10) })
    expect(line(e)).toBe('29 Oct, 14:10 · Pass 1 → Pass 1, Later · from the library menu')
  })
  it('keeps level and decision together on both sides of the arrow', () => {
    const e = event({ source: 'reader', before_pass: 1, before_triage: 'later', after_pass: 2, after_triage: 'keep' })
    expect(describeEvent(e).what).toBe('Pass 1, Later → Pass 2, Keep')
  })
  it('reads a reader change and a drop from the library without a reason', () => {
    expect(line(event({ source: 'reader', before_triage: 'keep', after_triage: null }))).toBe(
      '29 Oct, 14:02 · Keep → Undecided · from the reader'
    )
    const drop = describeEvent(event({ source: 'library', before_triage: null, after_triage: 'drop' }))
    expect([drop.what, drop.why]).toEqual(['Undecided → Dropped', null])
  })
  it('reads an undo', () => {
    const e = event({ source: 'undo', before_triage: 'drop', after_triage: null, undone_event_id: 'e0' })
    expect(describeEvent(e)).toMatchObject({ what: 'Undone: Dropped → Undecided', where: 'by undoing' })
  })
  it('adds PDF opened, with minutes only when above zero', () => {
    expect(describeEvent(event({ pdf_opened: true, pdf_ms: 0 })).why).toBe('PDF opened')
    expect(describeEvent(event({ pdf_opened: true, pdf_ms: null })).why).toBe('PDF opened')
    expect(describeEvent(event({ pdf_opened: true, pdf_ms: 150000 })).why).toBe('PDF opened, 3 min')
    expect(describeEvent(event({ pdf_opened: false, pdf_ms: 150000 })).why).toBeNull()
  })
})
