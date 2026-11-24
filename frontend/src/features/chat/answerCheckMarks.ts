import type { AnswerCheckSentence } from '@/entities'

export type Tone = 'quiet' | 'warn' | 'bad' | 'muted'
export type Chip = { symbol: string; word: string; tone: Tone }

const VERDICTS: Record<NonNullable<AnswerCheckSentence['verdict']>, Chip> = {
  supported: { symbol: '✓', word: 'Supported', tone: 'quiet' },
  partially_supported: { symbol: '◐', word: 'Partly supported', tone: 'warn' },
  not_supported: { symbol: '✗', word: 'Not supported', tone: 'bad' },
  not_addressed: { symbol: '?', word: 'Not addressed', tone: 'bad' },
  couldnt_check: { symbol: '·', word: "Couldn't check", tone: 'muted' },
}

const STATES: Record<Exclude<AnswerCheckSentence['state'], 'done'>, Chip> = {
  pending: { symbol: '…', word: 'Checking', tone: 'muted' },
  not_cited: { symbol: '·', word: 'Not cited', tone: 'muted' },
  not_checked: { symbol: '·', word: 'Not checked (limit)', tone: 'muted' },
  not_kept: { symbol: '·', word: 'Not checked (passage not kept)', tone: 'muted' },
}

/** A sentence's mark: always a symbol and a word, never colour alone. */
export function chip(sentence: AnswerCheckSentence): Chip {
  if (sentence.state === 'done') return VERDICTS[sentence.verdict ?? 'couldnt_check']
  return STATES[sentence.state]
}
