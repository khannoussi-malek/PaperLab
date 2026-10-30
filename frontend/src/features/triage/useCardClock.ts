import { useEffect, useMemo, useState } from 'react'
import { CardClock } from './cardClock'

/** The clock of the card on top: fresh for every card, running only while the tab is visible and focused. */
export function useCardClock(cardId: string | undefined, { pdfShown }: { pdfShown: boolean }, now?: () => number) {
  const [clock] = useState(() => new CardClock(now))
  useEffect(() => clock.reset(), [cardId, clock])
  useEffect(() => clock.setPdfShown(pdfShown), [pdfShown, clock])
  useEffect(() => {
    let focused = document.hasFocus()
    const sync = () => clock.setActive(document.visibilityState === 'visible' && focused)
    const focus = () => { focused = true; sync() }
    const blur = () => { focused = false; sync() }
    sync()
    document.addEventListener('visibilitychange', sync)
    window.addEventListener('focus', focus)
    window.addEventListener('blur', blur)
    return () => {
      document.removeEventListener('visibilitychange', sync)
      window.removeEventListener('focus', focus)
      window.removeEventListener('blur', blur)
    }
  }, [clock])
  return useMemo(() => ({ read: () => clock.read(), interact: () => clock.interact() }), [clock])
}
