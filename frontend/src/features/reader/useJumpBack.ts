import { useState, type RefObject, type UIEvent } from 'react'

/**
 * Q1 (b): where a citation jump left from. `away` turns true once the jump has scrolled at least half a screen from
 * it; `id` tells one jump from the next.
 */
export type JumpSpot = { id: number; scrollTop: number; page: number; citationId: string; viaKeyboard: boolean; away: boolean }

/**
 * The spot after the pages scrolled to `scrollTop` in a `screen`-high view: armed once the jump is half a screen away,
 * and gone (null) once the reader comes back within half a screen by hand.
 */
export function afterScroll(spot: JumpSpot, scrollTop: number, screen: number): JumpSpot | null {
  const near = Math.abs(scrollTop - spot.scrollTop) < screen / 2
  if (!spot.away) return near ? spot : { ...spot, away: true }
  return near ? null : spot
}

/** The citation button a keyboard jump came from, to give focus back to after Back. */
const citationButton = (citationId: string) =>
  document.querySelector<HTMLButtonElement>(`[data-citation-id="${citationId}"] .citation-link`)

/** The reader's way back from a citation jump (Q1-b). `pages` is the scrolling pages section. */
export function useJumpBack(pages: RefObject<HTMLElement | null>) {
  const [spot, setSpot] = useState<JumpSpot | null>(null)

  /** Before a jump: remember the pages' scroll offset and the citation's page. A later jump replaces it. */
  function save(citation: { id: string; page: number }, viaKeyboard: boolean) {
    const scrollTop = pages.current?.scrollTop ?? 0
    setSpot({ id: Date.now(), scrollTop, page: citation.page, citationId: citation.id, viaKeyboard, away: false })
  }

  function onScroll(event: UIEvent<HTMLElement>) {
    if (!spot) return
    const next = afterScroll(spot, event.currentTarget.scrollTop, event.currentTarget.clientHeight)
    if (next !== spot) setSpot(next)
  }

  /** Back to the spot, smoothly; after a keyboard jump, focus goes back to the citation too. */
  function back() {
    if (!spot) return
    pages.current?.scrollTo({ top: spot.scrollTop, behavior: 'smooth' })
    if (spot.viaKeyboard) citationButton(spot.citationId)?.focus({ preventScroll: true })
    setSpot(null)
  }

  return { spot, save, onScroll, back }
}
