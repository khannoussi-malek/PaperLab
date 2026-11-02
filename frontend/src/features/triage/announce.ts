import { paperLabel } from '@/features/library/paperMeta'
import { FIVE_CS, LATE_CHIP_KEYS, offersReason, PILES, REASONS, type Pile } from './piles'

type Who = Parameters<typeof paperLabel>[0]

export const chipRowCount = REASONS.not_relevant.length

/** `index` is 0-based. */
export const newCard = (paper: Who, index: number, total: number) =>
  `${paperLabel(paper)}. Paper ${index + 1} of ${total}. Undecided. Abstract below.`

const reasonLabel = (pile: Pile, reason: string) => REASONS[pile].find((x) => x.key === reason)?.label ?? reason.replaceAll('_', ' ')

export function decided(paper: Who, pile: Pile, reason: string | undefined, done: number, total: number) {
  const what = pile === 'skip' ? 'Skipped' : PILES[pile].label
  const why = reason ? `, ${reasonLabel(pile, reason)}` : ''
  const offer = offersReason(pile) && !reason ? ` Reason optional: ${LATE_CHIP_KEYS.slice(0, -1).join(', ')} or ${LATE_CHIP_KEYS.at(-1)}.` : ''
  return `${paperLabel(paper)}. ${what}${why}. ${done} of ${total} done.${offer}`
}

export const reasonAdded = (pile: Pile, reason: string) => `Reason added: ${reasonLabel(pile, reason)}.`
export const fiveCsOpen = 'Five Cs open. 1 to 5 tick, C closes.'
export const fiveCsClosed = 'Five Cs closed.'
export const fiveCsTick = (i: number, on: boolean) => `${FIVE_CS[i].split(':')[0]} ${on ? 'ticked' : 'unticked'}.`

export const undone = (paper: Who) => `${paperLabel(paper)}. Decision undone. Undecided.`
export const failed = (message: string) => `That decision did not save. ${message}`
export const reasonRow = () => `Pick a reason, 1 to ${chipRowCount}`
