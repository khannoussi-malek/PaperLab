import { useEffect, useRef, useState, type RefObject, type UIEvent } from 'react'

/**
 * Where a citation jump left from. `away` turns true once the jump has scrolled at least half a screen from it;
 * `id` tells one jump from the next; `scale` is the zoom it was captured at, since `scrollTop` only means the
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

/** The citation button a keyboard jump came from, to give focus back to after Back (or if the pill unmounts while it holds focus). */
const citationButton = (citationId: string) =>
  document.querySelector<HTMLButtonElement>(`[data-citation-id="${citationId}"] .citation-link`)

/** The reader's way back from a citation jump. `pages` is the scrolling pages section, `scale` its current zoom. */
export function useJumpBack(pages: RefObject<HTMLElement | null>, scale: number) {
  const [saved, setSaved] = useState<JumpSpot | null>(null)
  const nextId = useRef(0)
  const pillRef = useRef<HTMLButtonElement>(null)
  // The id of the spot the pill has already taken initial focus for, so a remount of the same spot (zooming away
  // and back) doesn't steal focus again; and the last spot seen, to know where to send focus back to if the pill
  // unmounts while still holding it.
  const focusedSpotId = useRef<number | null>(null)
  const lastSpot = useRef<JumpSpot | null>(null)
  // Derived, not stored: a zoom change is caught on the very next render, no effect needed, and a saved spot from a
  // stale zoom can never leak into `back()`.
  const spot = forScale(saved, scale)

  // The pill takes focus once per spot, the first time it appears for a keyboard jump. If it then unmounts while it
  // still holds that focus (scrolled back by hand, or zoomed away), focus drops to <body>: send it back to the
  // citation button that jumped, the same one Back returns focus to. Focus that has already moved elsewhere on its
  // own (the Zoom button, say) is left alone.
  useEffect(() => {
    const previous = lastSpot.current
    lastSpot.current = spot
    if (spot) {
      if (spot.viaKeyboard && focusedSpotId.current !== spot.id) {
        pillRef.current?.focus()
        focusedSpotId.current = spot.id
      }
      return
    }
    if (previous && focusedSpotId.current === previous.id && document.activeElement === document.body) {
      citationButton(previous.citationId)?.focus({ preventScroll: true })
    }
  }, [spot])

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

  return { spot, pillRef, save, onScroll, back }
}
