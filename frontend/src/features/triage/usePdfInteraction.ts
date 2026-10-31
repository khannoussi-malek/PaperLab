import { useEffect, useRef, type RefObject } from 'react'

const INPUT_WINDOW_MS = 300
const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

/** A scroll counts as the reader's only when input came just before it; reflow and re-placing scroll alone. */
export const isUserScroll = (lastInputAt: number | null, now: number) => lastInputAt !== null && now - lastInputAt <= INPUT_WINDOW_MS

/** Reports the reader's scrolling and text selection in the scroller. Zoom and page changes call `onInteract` themselves. */
export function usePdfInteraction(scrollerRef: RefObject<HTMLElement | null>, onInteract: () => void) {
  const latest = useRef(onInteract)
  useEffect(() => { latest.current = onInteract })
  useEffect(() => {
    const box = scrollerRef.current
    if (!box) return
    let lastInput: number | null = null
    const input = () => { lastInput = performance.now() }
    const key = (e: KeyboardEvent) => { if (SCROLL_KEYS.has(e.key)) input() }
    const scroll = () => { if (isUserScroll(lastInput, performance.now())) latest.current() }
    const select = () => {
      const sel = window.getSelection()
      if (sel && !sel.isCollapsed && sel.anchorNode && box.contains(sel.anchorNode)) latest.current()
    }
    box.addEventListener('wheel', input, { passive: true })
    box.addEventListener('touchmove', input, { passive: true })
    box.addEventListener('pointerdown', input)
    box.addEventListener('keydown', key)
    box.addEventListener('scroll', scroll)
    document.addEventListener('selectionchange', select)
    return () => {
      box.removeEventListener('wheel', input)
      box.removeEventListener('touchmove', input)
      box.removeEventListener('pointerdown', input)
      box.removeEventListener('keydown', key)
      box.removeEventListener('scroll', scroll)
      document.removeEventListener('selectionchange', select)
    }
  }, [scrollerRef])
}
