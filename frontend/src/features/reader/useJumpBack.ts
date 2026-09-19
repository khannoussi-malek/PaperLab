import { useRef, useState, type RefObject, type UIEvent } from 'react'

/**
 * Q1 (b): where a citation jump left from. `away` turns true once the jump has scrolled at least half a screen from
 * it; `id` tells one jump from the next; `scale` is the zoom it was captured at, since `scrollTop` only means the
 * same place at that zoom.
 */
export type JumpSpot = {
  id: number
  scrollTop: number
  page: number
  citationId: string
  viaKeyboard: boolean
  away: boolean
  scale: number
}

/**
 * The spot after the pages scrolled to `scrollTop` in a `screen`-high view: armed once the jump is half a screen away,
 * and gone (null) once the reader comes back within half a screen by hand.
 */
export function afterScroll(spot: JumpSpot, scrollTop: number, screen: number): JumpSpot | null {
  const near = Math.abs(scrollTop - spot.scrollTop) < screen / 2
  if (!spot.away) return near ? spot : { ...spot, away: true }
  return near ? null : spot
}

/** A spot saved at a different zoom than `scale`: its `scrollTop` no longer means the same place, so it's dropped. */
export function forScale(spot: JumpSpot | null, scale: number): JumpSpot | null {
  return spot && spot.scale === scale ? spot : null
}

/** The citation button a keyboard jump came from, to give focus back to after Back. */
const citationButton = (citationId: string) =>
  document.querySelector<HTMLButtonElement>(`[data-citation-id="${citationId}"] .citation-link`)

/** The reader's way back from a citation jump (Q1-b). `pages` is the scrolling pages section, `scale` its current zoom. */
export function useJumpBack(pages: RefObject<HTMLElement | null>, scale: number) {
  const [saved, setSaved] = useState<JumpSpot | null>(null)
  const nextId = useRef(0)
  // Derived, not stored: a zoom change is caught on the very next render, no effect needed, and a saved spot from a
  // stale zoom can never leak into `back()`.
  const spot = forScale(saved, scale)

  /** Before a jump: remember the pages' scroll offset, the citation's page, and the zoom it was seen at. A later jump replaces it. */
  function save(citation: { id: string; page: number }, viaKeyboard: boolean) {
    const scrollTop = pages.current?.scrollTop ?? 0
    nextId.current += 1 // not Date.now(): two jumps inside one millisecond must still get different ids
    setSaved({ id: nextId.current, scrollTop, page: citation.page, citationId: citation.id, viaKeyboard, away: false, scale })
  }

  function onScroll(event: UIEvent<HTMLElement>) {
    if (!spot) return
    const next = afterScroll(spot, event.currentTarget.scrollTop, event.currentTarget.clientHeight)
    if (next !== spot) setSaved(next)
  }

  /** Back to the spot, smoothly; after a keyboard jump, focus goes back to the citation too. */
  function back() {
    if (!spot) return
    pages.current?.scrollTo({ top: spot.scrollTop, behavior: 'smooth' })
    if (spot.viaKeyboard) citationButton(spot.citationId)?.focus({ preventScroll: true })
    setSaved(null)
  }

  return { spot, save, onScroll, back }
}
