import { expect, test } from 'vitest'
import type { DraftReview, DraftReviewEstimate } from '@/api/client'
import { discardedCount, isLive, modeText, reasonText, severityLabel, startBody } from './draftReviewModel'

test('a failed review reason in plain words; an unknown one is not blamed on the model', () => {
  expect(reasonText('paper_too_short')).toBe('There is not enough text to review yet.')
  expect(reasonText('paper_too_long')).toBe('The draft is too long to review at once.')
  expect(reasonText('model_unavailable')).toBe('The model could not be reached.')
  expect(reasonText('model_error')).toBe("The model's answer could not be used. Try again.")
  expect(reasonText('cancelled')).toBe('Cancelled.')
  expect(reasonText('queue_unavailable')).toBe('The worker is not running.')
  expect(reasonText('something_new')).toBe('The review failed. Try again.')
  expect(reasonText(null)).toBe('The review failed. Try again.')
})

test('severity labels for the four levels', () => {
  expect(severityLabel('blocker')).toBe('Blocker')
  expect(severityLabel('major')).toBe('Major')
  expect(severityLabel('minor')).toBe('Minor')
  expect(severityLabel('nit')).toBe('Nit')
})

test('each mode estimate in plain words', () => {
  const light: DraftReviewEstimate['modes'][number] = { mode: 'light', likely_calls: 8, max_calls: 11, approx_input_tokens: 9000 }
  const full: DraftReviewEstimate['modes'][number] = { mode: 'full', likely_calls: 42, max_calls: 54, approx_input_tokens: 90000 }
  expect(modeText(light)).toBe('Light: up to 11 model calls, about 10 to 15 minutes on a local model.')
  expect(modeText(full)).toBe('Full: about 42 model calls, at most 54, up to an hour or more on a local model.')
})

test('the start request body carries both confirmations', () => {
  expect(startBody('light', false, false)).toEqual({ mode: 'light', confirm_remote: false, confirm_full: false })
  expect(startBody('full', true, true)).toEqual({ mode: 'full', confirm_remote: true, confirm_full: true })
})

test('only queued and running reviews are live', () => {
  const at = (status: DraftReview['status']) => ({ status }) as Pick<DraftReview, 'status'>
  expect(isLive(at('queued'))).toBe(true)
  expect(isLive(at('running'))).toBe(true)
  expect(isLive(at('done'))).toBe(false)
  expect(isLive(at('failed'))).toBe(false)
  expect(isLive(at('interrupted'))).toBe(false)
  expect(isLive(null)).toBe(false)
})

test('discarded points are the four drop counters only', () => {
  expect(discardedCount({ dropped_invalid: 2, dropped_criterion: 1, dropped_quote: 3, dropped_wording: 4 })).toBe(10)
  expect(discardedCount({ dropped_seen: 5, over_cap: 2, reasons_masked: 1 })).toBe(0)
  expect(discardedCount({})).toBe(0)
})
