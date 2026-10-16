import { expect, test } from 'vitest'
import { continueRefusal } from './continueText'

test('the three refusals read in plain words, anything else stays raw', () => {
  expect(continueRefusal('nothing_left_to_fetch')).toBe('Every source is already finished.')
  expect(continueRefusal('search_run_already_running')).toBe('This search is already running.')
  expect(continueRefusal('search_run_still_stopping')).toBe('Still stopping the last pass; try again in a few seconds.')
  expect(continueRefusal('boom')).toBe('boom')
})
