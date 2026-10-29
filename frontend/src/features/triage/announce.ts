import { paperLabel } from '@/features/library/paperMeta'
import { PILES, REASONS, type Pile } from './piles'

type Who = Parameters<typeof paperLabel>[0]

export const chipRowCount = REASONS.not_relevant.length

/** `index` is 0-based. */
export const newCard = (paper: Who, index: number, total: number) =>
  `${paperLabel(paper)}. Paper ${index + 1} of ${total}. Undecided. Abstract below.`

export function decided(paper: Who, pile: Pile, reason: string | undefined, done: number, total: number) {
  const what = pile === 'skip' ? 'Skipped' : PILES[pile].label
  const why = reason ? `, ${REASONS[pile].find((x) => x.key === reason)?.label ?? reason.replaceAll('_', ' ')}` : ''
  return `${paperLabel(paper)}. ${what}${why}. ${done} of ${total} done.`
}

export const undone = (paper: Who) => `${paperLabel(paper)}. Decision undone. Undecided.`
export const failed = (message: string) => `That decision did not save. ${message}`
export const reasonRow = () => `Pick a reason, 1 to ${chipRowCount}`
