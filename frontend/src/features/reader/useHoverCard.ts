import { useEffect, useRef, useState } from 'react'

/** Grace period for the pointer to travel between a highlight and its card. */
export const HOVER_CLOSE_DELAY_MS = 300

export type HoverTarget = { page: number; noteIds: string[] }

/**
 * Which notes the hover card shows. Pointing at a highlight shows them at once; leaving both the highlight
 * and the card closes the card after HOVER_CLOSE_DELAY_MS. While `locked` (a note in the card is being
 * edited) the card neither closes nor switches to other notes.
 */
export function useHoverCard(locked: boolean) {
  const [target, setTarget] = useState<HoverTarget | null>(null)
  const closeTimer = useRef<number | null>(null)

  function stay() {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current)
    closeTimer.current = null
  }

  useEffect(
    () => () => {
      if (closeTimer.current !== null) window.clearTimeout(closeTimer.current)
    },
    [],
  )

  /** The pointer is over these notes' highlight. Returns true when the card now shows different notes. */
  function show(next: HoverTarget): boolean {
    stay()
    const same = target?.page === next.page && target.noteIds.join() === next.noteIds.join()
    if (locked || same) return false
    setTarget(next)
    return true
  }

  /** The pointer is over neither a highlight nor the card: close soon, unless already closing or locked. */
  function leave() {
    if (locked || target === null || closeTimer.current !== null) return
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null
      setTarget(null)
    }, HOVER_CLOSE_DELAY_MS)
  }

  function close() {
    stay()
    setTarget(null)
  }

  return { target, show, leave, stay, close }
}
