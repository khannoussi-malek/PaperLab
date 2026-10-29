import { useEffect, useRef, type RefObject } from 'react'
import { pileForDrag, type Pile } from './piles'

type Opts = {
  enabled: boolean
  min?: number
  reduced?: boolean
  onProgress: (dx: number, dy: number, pile: Pile | null) => void
  onCommit: (pile: Pile) => void
  onCancel: () => void
}

// Text selection, button clicks and the abstract's scrolling keep their own gestures.
const NO_DRAG = 'button,a,input,select,textarea,[aria-label="Abstract"]'

/** Pointer drag on the card: past `min` px a release decides the pile, less snaps back. Esc cancels. */
export function useCardDrag(ref: RefObject<HTMLElement | null>, opts: Opts) {
  const latest = useRef(opts)
  useEffect(() => { latest.current = opts })
  const { enabled } = opts

  useEffect(() => {
    const el = ref.current
    if (!el || !enabled) return
    let start: { x: number; y: number; id: number } | null = null
    let moved = false
    let prevSelect = ''

    const reset = () => {
      const { reduced } = latest.current
      el.style.transition = reduced ? 'none' : 'transform 200ms ease-out'
      el.style.transform = ''
    }
    const end = () => {
      start = null
      moved = false
      document.body.style.userSelect = prevSelect
      window.removeEventListener('keydown', onKey, true)
    }
    const cancel = () => {
      end()
      reset()
      latest.current.onCancel()
    }
    function onKey(e: KeyboardEvent) {
      // capture + stop: Esc ends the drag only, the desk's own Esc (leave) must not also fire
      if (e.key === 'Escape') { e.stopPropagation(); cancel() }
    }
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0 || start || (e.target as Element).closest(NO_DRAG)) return
      start = { x: e.clientX, y: e.clientY, id: e.pointerId }
      el.setPointerCapture?.(e.pointerId)
      el.style.transition = 'none'
      prevSelect = document.body.style.userSelect
      document.body.style.userSelect = 'none'
      window.addEventListener('keydown', onKey, true)
    }
    const onMove = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return
      moved = true
      const dx = e.clientX - start.x
      const dy = e.clientY - start.y
      el.style.transform = `translate(${dx}px, ${dy}px) rotate(${dx / 14}deg)`
      latest.current.onProgress(dx, dy, pileForDrag(dx, dy, latest.current.min))
    }
    const onUp = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return
      const pile = pileForDrag(e.clientX - start.x, e.clientY - start.y, latest.current.min)
      if (!pile) return moved ? cancel() : (end(), reset())
      end()
      el.style.transition = 'none'
      el.style.transform = ''
      latest.current.onCommit(pile)
    }
    el.addEventListener('pointerdown', onDown)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', cancel)
    return () => {
      el.removeEventListener('pointerdown', onDown)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerup', onUp)
      el.removeEventListener('pointercancel', cancel)
      window.removeEventListener('keydown', onKey, true)
      if (start) document.body.style.userSelect = prevSelect
    }
  }, [ref, enabled])
}
