import { useState } from 'react'
import * as say from './announce'

type Card = { open: boolean; mask: number | null }
const UNTOUCHED: Card = { open: false, mask: null }

/**
 * The checklist's state per paper for this desk session, in memory only. A next card starts untouched; an undo or a failed
 * save brings a card back as it was left, because the reader's answers are still true of that paper.
 * `mask` stays null until the group is first opened, so "never looked" differs from "looked, ticked none" (0).
 */
export function useFiveCs(paperId: string | undefined, announce: (text: string) => void) {
  const [cards, setCards] = useState<Record<string, Card>>({})
  const card = (paperId ? cards[paperId] : undefined) ?? UNTOUCHED
  const put = (id: string, next: Card) => setCards((all) => ({ ...all, [id]: next }))
  return {
    ...card,
    toggle: () => {
      if (!paperId) return
      put(paperId, { open: !card.open, mask: card.mask ?? 0 })
      announce(card.open ? say.fiveCsClosed : say.fiveCsOpen)
    },
    tick: (n: number) => {
      if (!paperId) return
      const bit = 1 << (n - 1)
      const mask = (card.mask ?? 0) ^ bit
      put(paperId, { ...card, mask })
      announce(say.fiveCsTick(n - 1, (mask & bit) !== 0))
    },
    reset: () => setCards({}),
  }
}
