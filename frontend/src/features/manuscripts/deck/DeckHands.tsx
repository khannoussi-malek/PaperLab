import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import HandsMode from '../../graph/hands/HandsMode'
import { hopAction, initialTotals, turnStep, zoomStep, type DeckAction } from './deckGestures'

/** No gesture acts this soon after a keystroke anywhere in the page. */
export const TYPING_PAUSE_MS = 2000

export const DECK_TEXT = {
  point: 'Pointing: hold still on a paper or tab to open it',
  two: 'Two fingers: flick left or right for the next or previous paper',
  palm: 'Open hand: move sideways to glide through the deck',
  'two-palms': 'Both hands: spread to open the paper, bring together to close it',
  fist: 'Fist: paused',
}
export const DECK_GESTURES = 'Point and hold to open · Two fingers and flick for next or previous · Open hand to glide · Both hands spread to open, together to close · Fist to pause.'
export const HANDS_HELP = 'The camera picture stays on this computer.'

export type DeckHandsProps = {
  /** The deck column: gestures act only while focus or the pointer is inside it. */
  column: RefObject<HTMLElement | null>
  onAction: (action: DeckAction) => void
  /** A hold on a card or a book tab. */
  onSelect: (id: string, kind: 'card' | 'tab') => void
  /** The column went out of sight (collapsed, or tabbed away): the camera is off and Hands must be turned on again. */
  onHidden: () => void
}

const TARGETS = '[data-deck-card],[data-book-tab]'

/** Hands mode over the deck column. It never edits text: it only moves the deck. */
export function DeckHands({ column, onAction, onSelect, onHidden }: DeckHandsProps) {
  const overlay = useRef<HTMLDivElement>(null)
  const totals = useRef(initialTotals)
  const [inDeck, setInDeck] = useState(false)
  const [typing, setTyping] = useState(false)
  const [hidden, setHidden] = useState(false)
  const hiddenCb = useRef(onHidden)
  hiddenCb.current = onHidden

  // StudioColumns keeps hidden columns mounted, so watch for [hidden] on the column or any ancestor.
  useEffect(() => {
    const check = () => {
      if (!column.current?.closest('[hidden]')) return
      setHidden(true)
      hiddenCb.current()
    }
    check()
    const observer = new MutationObserver(check)
    observer.observe(document.body, { attributes: true, attributeFilter: ['hidden'], subtree: true })
    return () => observer.disconnect()
  }, [column])

  // Resuming after any pause starts the totals afresh, so it cannot fire a step at once.
  const idle = !inDeck || typing
  useEffect(() => { totals.current = initialTotals }, [idle])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const within = (t: EventTarget | null) => t instanceof Node && !!column.current?.contains(t)
    const onKey = () => {
      setTyping(true)
      clearTimeout(timer)
      timer = setTimeout(() => setTyping(false), TYPING_PAUSE_MS)
    }
    const track = (e: Event) => setInDeck(within(e.target))
    const away = () => setInDeck(false)
    const col = column.current
    col?.addEventListener('pointerleave', away)
    window.addEventListener('blur', away)
    const focusOut = () => setInDeck(within(document.activeElement))
    document.addEventListener('keydown', onKey, true)
    document.addEventListener('pointerover', track)
    document.addEventListener('focusin', track)
    document.addEventListener('focusout', focusOut)
    setInDeck(within(document.activeElement))
    return () => {
      clearTimeout(timer)
      document.removeEventListener('keydown', onKey, true)
      document.removeEventListener('pointerover', track)
      document.removeEventListener('focusin', track)
      document.removeEventListener('focusout', focusOut)
      col?.removeEventListener('pointerleave', away)
      window.removeEventListener('blur', away)
    }
  }, [column])

  const pickAt = useCallback((x: number, y: number) => {
    const r = overlay.current?.getBoundingClientRect()
    if (!r) return null
    const el = document.elementFromPoint(r.left + x * r.width, r.top + y * r.height)?.closest(TARGETS)
    if (!el) return null
    const id = el.getAttribute('data-deck-card') ?? el.getAttribute('data-book-tab')!
    return { id, title: el.getAttribute('aria-label') ?? el.querySelector('b')?.textContent ?? el.textContent ?? '' }
  }, [])

  const run = (next: ReturnType<typeof turnStep>) => {
    totals.current = next[0]
    if (next[1]) onAction(next[1])
  }

  if (hidden) return null
  return (
    <div ref={overlay} className="pointer-events-none absolute inset-0 z-20">
      <HandsMode
        paused={idle}
        text={DECK_TEXT}
        gestures={DECK_GESTURES}
        pickAt={pickAt}
        onSelect={(id) => onSelect(id, document.querySelector(`[data-book-tab="${CSS.escape(id)}"]`) ? 'tab' : 'card')}
        onHop={(step) => onAction(hopAction(step))}
        onTurn={(azimuth) => run(turnStep(totals.current, azimuth))}
        onZoom={(factor) => run(zoomStep(totals.current, factor))}
      />
    </div>
  )
}
