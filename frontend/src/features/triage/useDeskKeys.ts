import { useEffect, useRef, type RefObject } from 'react'
import { pileForKey, type Pile } from './piles'

export type DeskKeyHandlers = {
  /** The reason chips are showing: 1-6 are reasons and the other pile keys sleep. */
  reasonsShowing: boolean
  helpOpen: boolean
  onPile: (pile: Pile) => void
  onReason: (n: number) => void
  cancelReason: () => void
  closeHelp: () => void
  exit: () => void
  undo: () => void
  togglePdf: () => void
  openHelp: () => void
  focusAbstract: () => void
  /** The pile whose key is held down (null on release or blur): its stamp shows. */
  onHold?: (pile: Pile | null) => void
}

// Where the element keeps its own keys: buttons, fields, the abstract scroller, anything in the PDF column.
const OWN = 'button,a,input,textarea,select,[contenteditable],[role="tab"],[aria-label="Abstract"],[data-triage-pdf]'
const TYPING = 'input,textarea,select,[contenteditable]'
const REGIONS = '[data-triage-region]:not([hidden])'

function cycleRegions(root: HTMLElement, back: boolean) {
  const regions = [...root.querySelectorAll<HTMLElement>(REGIONS)]
  if (regions.length === 0) return false
  const at = regions.findIndex((r) => r.contains(document.activeElement))
  const n = regions.length
  regions[at === -1 ? (back ? n - 1 : 0) : (at + (back ? -1 : 1) + n) % n].focus()
  return true
}

/**
 * The desk's ONE keydown listener, on the desk root (a native one, so portalled popups never reach it).
 * Pile keys (arrows, 1-5, Space) and A fire only outside buttons, fields, the abstract and the PDF column;
 * there only Esc, P, F6, ? and U are the desk's; in a text field only Esc is. Other chords are ignored.
 */
export function useDeskKeys(rootRef: RefObject<HTMLElement | null>, handlers: DeskKeyHandlers) {
  const latest = useRef(handlers)
  useEffect(() => { latest.current = handlers })

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as Element
      if (e.defaultPrevented || !(target instanceof Element)) return
      const h = latest.current
      const typing = target.closest(TYPING) !== null
      const own = target.closest(OWN) !== null
      const done = () => e.preventDefault()
      const k = e.key
      const mod = e.ctrlKey || e.metaKey
      if (e.altKey) return
      if (k === 'Escape' && !mod) {
        done()
        if (h.reasonsShowing) h.cancelReason()
        else if (h.helpOpen) h.closeHelp()
        else h.exit()
        return
      }
      if (k === 'F6' && !mod) {
        if (cycleRegions(root, e.shiftKey)) done()
        return
      }
      if (typing) return
      if (mod) {
        if (k.toLowerCase() === 'z' && !e.shiftKey) { done(); h.undo() }
        return
      }
      if (k === '?') { done(); h.openHelp(); return }
      if (e.shiftKey) return
      const lower = k.toLowerCase()
      if (lower === 'p') { done(); h.togglePdf(); return }
      if (lower === 'u') { done(); h.undo(); return }
      if (own || e.repeat) return
      if (h.reasonsShowing) {
        if (/^[1-6]$/.test(k)) { done(); h.onReason(Number(k)) }
        return
      }
      if (lower === 'a') { done(); h.focusAbstract(); return }
      const pile = pileForKey(k)
      if (pile) { done(); h.onHold?.(pile); h.onPile(pile) }
    }
    const release = () => latest.current.onHold?.(null)
    root.addEventListener('keydown', onKey)
    root.addEventListener('keyup', release)
    window.addEventListener('blur', release)
    return () => {
      root.removeEventListener('keydown', onKey)
      root.removeEventListener('keyup', release)
      window.removeEventListener('blur', release)
    }
  }, [rootRef])
}
