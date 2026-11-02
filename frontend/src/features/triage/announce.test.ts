import { describe, expect, it } from 'vitest'
import { chipRowCount, decided, failed, fiveCsTick, newCard, reasonAdded, reasonRow, undone } from './announce'

const paper = { title: 'T', authors: ['Patrick Lewis'], year: 2020 }

describe('announce', () => {
  it('a new card', () => {
    expect(newCard(paper, 2, 60)).toBe('Lewis 2020. Paper 3 of 60. Undecided. Abstract below.')
  })
  it('each outcome', () => {
    expect(decided(paper, 'skim', undefined, 4, 60)).toBe('Lewis 2020. Skim. 4 of 60 done. Reason optional: 7, 8 or 9.')
    expect(decided(paper, 'not_relevant', 'off_topic', 4, 60)).toBe('Lewis 2020. Not relevant, off-topic. 4 of 60 done.')
    expect(decided(paper, 'skip', undefined, 4, 60)).toBe('Lewis 2020. Skipped. 4 of 60 done.')
    expect(undone(paper)).toBe('Lewis 2020. Decision undone. Undecided.')
    expect(failed('Network down')).toBe('That decision did not save. Network down')
    expect(reasonRow()).toBe('Pick a reason, 1 to 6')
    expect(chipRowCount).toBe(6)
    expect(reasonAdded('later', 'needs_background')).toBe('Reason added: needs background first.')
    expect(fiveCsTick(0, true)).toBe('Category ticked.')
    expect(fiveCsTick(4, false)).toBe('Clarity unticked.')
  })
})
