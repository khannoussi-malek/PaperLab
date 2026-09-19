import { useEffect, useRef, useState } from 'react'

/** Grace period for the pointer to travel between a highlight and its card. */
export const HOVER_CLOSE_DELAY_MS = 300

/**
 * What the reader's one hover card shows (D147): notes (`editNoteId` opens that note straight in edit mode, from the
 * right-click menu) or one citation.
 */
export type HoverTarget =
  | { kind: 'notes'; page: number; noteIds: string[]; editNoteId?: string }
  | { kind: 'citation'; page: number; citationId: string }

/** The same kind, page and ids: the card already shows it. */
export function sameTarget(a: HoverTarget | null, b: HoverTarget): boolean {
  if (a === null || a.kind !== b.kind || a.page !== b.page) return false
  if (a.kind === 'citation' && b.kind === 'citation') return a.citationId === b.citationId
  return a.kind === 'notes' && b.kind === 'notes' && a.noteIds.join() === b.noteIds.join()
}

/**
 * What the reader's hover card shows. Pointing at a highlight or a citation shows it at once; leaving both it and the
 * card closes the card after HOVER_CLOSE_DELAY_MS. While `locked` (a note in the card is being edited) the card
 * neither closes nor switches to anything else, a citation included.
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

  /** The pointer is over these notes' highlight, or a citation. Returns true when the card now shows something else. */
  function show(next: HoverTarget): boolean {
    stay()
    if (locked || sameTarget(target, next)) return false
    setTarget(next)
    return true
  }

  /** The pointer is over neither what the card shows nor the card: close soon, unless already closing or locked. */
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

  /** Show exactly this target now, regardless of the pointer. */
  function open(next: HoverTarget) {
    stay()
    setTarget(next)
  }

  return { target, show, leave, stay, close, open }
}
