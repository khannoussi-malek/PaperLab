import { CircleDashed, Check, TriangleAlert } from 'lucide-react'
import { expect, test } from 'vitest'
import type { SectionReview, SectionSpan } from '@/api/client'
import { failedReason, FINDING_ICON, FINDING_LABEL, findingTone, groupFindings, REVIEWABLE_ROLES, refChip, ROLE_LABEL, sectionAt, staleReviews, statusLine } from './sectionReviewModel'

const review = (o: Partial<SectionReview> = {}): SectionReview => ({ id: 'r1', file: 'main.tex', section_hash: 'h1', title: 'Method', role: 'method', role_source: 'guessed', status: 'done', reason: null, findings: [], dropped: 0, model: 'm', ai: true, created_at: '2026-10-31T00:00:00Z', ...o })
const span = (hash: string, start: number, end: number): SectionSpan => ({ title: hash, start, end, hash, words: 10, guess: 'method' })

test('labels, icons and tones for each finding kind', () => {
  expect(FINDING_LABEL).toEqual({ missing: 'Missing', unsupported: 'Unsupported', supported: 'Supported' })
  expect(FINDING_ICON).toEqual({ missing: CircleDashed, unsupported: TriangleAlert, supported: Check })
  expect([findingTone('missing'), findingTone('unsupported'), findingTone('supported')]).toEqual(['warn', 'bad', 'good'])
})

test('the picker offers the eight reviewable roles in reading order, in words', () => {
  expect(REVIEWABLE_ROLES).toEqual(['abstract', 'intro', 'related', 'method', 'results', 'discussion', 'limitations', 'conclusion'])
  expect(REVIEWABLE_ROLES.map((r) => ROLE_LABEL[r])).toContain('Related work')
})

test('findings group Missing, Unsupported, Supported, empty groups left out', () => {
  const f = (kind: 'missing' | 'unsupported' | 'supported', point: string) => ({ kind, point, refs: [] })
  const groups = groupFindings(review({ findings: [f('supported', 'a'), f('missing', 'b'), f('missing', 'c')] }))
  expect(groups.map((g) => [g.kind, g.findings.map((x) => x.point)])).toEqual([['missing', ['b', 'c']], ['supported', ['a']]])
  expect(groupFindings(review())).toEqual([])
})

test('a review is stale when its section hash is in no span, a running one too', () => {
  const a = review({ id: 'a', section_hash: 'h1' }), b = review({ id: 'b', section_hash: 'h2', status: 'running' }), c = review({ id: 'c', section_hash: 'h3' })
  expect(staleReviews([span('h1', 0, 10), span('h3', 10, 20)], [a, b, c])).toEqual([b])
  expect(staleReviews([], [a])).toEqual([a])
})

test('the section under the cursor: start inclusive, end exclusive, except the very end of the last', () => {
  const spans = [span('a', 0, 10), span('b', 10, 20)]
  expect(sectionAt(spans, 0)?.hash).toBe('a')
  expect(sectionAt(spans, 9)?.hash).toBe('a')
  expect(sectionAt(spans, 10)?.hash).toBe('b')
  expect(sectionAt(spans, 20)?.hash).toBe('b')
  expect(sectionAt(spans, 21)).toBeNull()
  expect(sectionAt([span('a', 5, 10)], 2)).toBeNull()
  expect(sectionAt([], 0)).toBeNull() // a main file with no sections
})

test('ref chips read S3 · first words… and Note · label', () => {
  expect(refChip({ kind: 'sentence', n: 3, hash: 'h', preview: 'The model was trained' })).toBe('S3 · The model was trained…')
  expect(refChip({ kind: 'sentence', n: 4, hash: 'h', preview: 'Sleep improves memory.' })).toBe('S4 · Sleep improves memory.')
  expect(refChip({ kind: 'sentence', n: 5, hash: 'h', preview: 'Is it (really?)' })).toBe('S5 · Is it (really?)')
  expect(refChip({ kind: 'note', n: 1, note_id: 'n', paper_id: 'p', label: 'Smith 2021 p.4' })).toBe('Note · Smith 2021 p.4')
  expect(refChip({ kind: 'note', n: 2, note_id: null, paper_id: null, label: null })).toBe('Note · note removed')
})

test('a one-line status per review, for the announcer', () => {
  const f = (kind: 'missing' | 'unsupported' | 'supported') => ({ kind, point: 'p', refs: [] })
  expect(statusLine(review({ status: 'queued', title: 'Method' }))).toBe('Reviewing “Method”…')
  expect(statusLine(review({ status: 'running', title: 'Method' }))).toBe('Reviewing “Method”…')
  expect(statusLine(review({ title: 'Method', findings: [f('missing'), f('missing'), f('unsupported'), f('supported')] }))).toBe('Review of “Method” done: 2 missing, 1 unsupported, 1 supported.')
  expect(statusLine(review({ status: 'failed', reason: 'model_error', title: 'Method' }))).toBe("Review of “Method” failed: The model didn't give a usable answer.")
  expect(statusLine(review({ status: 'failed', reason: 'cancelled', title: 'Method' }))).toBe('Review of “Method” failed: Cancelled.')
  expect(statusLine(review({ status: 'interrupted', title: 'Method' }))).toBe('Review of “Method” was interrupted.')
})

test('a review stopped because the default model turned remote says to start again', () => {
  expect(failedReason('remote_model_needs_confirm')).toBe('The default model is now a cloud model. Start again to confirm sending your text.')
})
