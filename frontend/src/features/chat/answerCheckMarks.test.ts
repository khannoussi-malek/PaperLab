import { describe, expect, it } from 'vitest'
import type { AnswerCheckSentence } from '@/entities'
import { chip } from './answerCheckMarks'

const sentence = (over: Partial<AnswerCheckSentence>): AnswerCheckSentence => ({
  index: 0,
  text: 'It is 5 mg.',
  labels: ['C1'],
  state: 'done',
  verdict: 'supported',
  reason: 'It says so.',
  quote: null,
  quote_label: null,
  confidence: 'high',
  shortened: false,
  ...over,
})

describe('chip', () => {
  it.each([
    [{ verdict: 'supported' as const }, '✓', 'Supported', 'quiet'],
    [{ verdict: 'partially_supported' as const }, '◐', 'Partly supported', 'warn'],
    [{ verdict: 'not_supported' as const }, '✗', 'Not supported', 'bad'],
    [{ verdict: 'not_addressed' as const }, '?', 'Not addressed', 'bad'],
    [{ verdict: 'couldnt_check' as const }, '·', "Couldn't check", 'muted'],
    [{ state: 'not_cited' as const, verdict: null }, '·', 'Not cited', 'muted'],
    [{ state: 'not_checked' as const, verdict: null }, '·', 'Not checked (limit)', 'muted'],
    [{ state: 'not_kept' as const, verdict: null }, '·', 'Not checked (passage not kept)', 'muted'],
    [{ state: 'pending' as const, verdict: null }, '…', 'Checking', 'muted'],
  ])('%o shows %s %s', (over, symbol, word, tone) => {
    expect(chip(sentence(over))).toEqual({ symbol, word, tone })
  })
})
