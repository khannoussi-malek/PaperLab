import { useEffect, type RefObject } from 'react'

const MODAL = '[role="dialog"][data-state="open"]'

/**
 * One rule for every path: when the focused element leaves the desk (removed, hidden, its panel closed), focus returns to
 * the desk root. Chromium fires `focusout` (relatedTarget null) before the element is gone, so the check runs a tick later.
 * A press outside the desk (a click on dead space or anything else) or focus moving to another element is left alone:
 * only a focus loss with no press outside since the desk last had focus pulls it back.
 */
export function useKeepDeskFocus(rootRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let inside = root.contains(document.activeElement)
    const check = () => {
      timer = undefined
      const active = document.activeElement
      if (root.isConnected && (active === null || active === document.body) && !document.querySelector(MODAL)) root.focus()
    }
    const schedule = () => {
      clearTimeout(timer)
      timer = setTimeout(check, 0)
    }
    const into = () => { inside = true }
    const out = (e: FocusEvent) => {
      if (e.relatedTarget !== null) { inside = root.contains(e.relatedTarget as Node); return }
      if (inside) schedule()
    }
    const press = (e: Event) => { inside = root.contains(e.target as Node) } // set before the focusout it causes
    // jsdom and some browsers drop focus on removal without a focusout: a change inside the desk is checked the same way
    const watch = new MutationObserver(() => { if (inside) schedule() })
    root.addEventListener('focusin', into)
    root.addEventListener('focusout', out)
    document.addEventListener('pointerdown', press, true)
    watch.observe(root, { childList: true, subtree: true })
    return () => {
      root.removeEventListener('focusin', into)
      root.removeEventListener('focusout', out)
      document.removeEventListener('pointerdown', press, true)
      watch.disconnect()
      clearTimeout(timer)
    }
  }, [rootRef])
}
