import { useEffect, type RefObject } from 'react'

/** One rule for every path: when the focused element is removed from inside the desk, focus returns to the desk root. */
export function useKeepDeskFocus(rootRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    let inside = root.contains(document.activeElement)
    const into = () => { inside = true }
    const out = (e: FocusEvent) => { if (e.relatedTarget === null && (e.target as Node).isConnected) inside = false }
    const watch = new MutationObserver(() => {
      if (inside && (document.activeElement === document.body || document.activeElement === null)) root.focus()
    })
    root.addEventListener('focusin', into)
    root.addEventListener('focusout', out)
    watch.observe(root, { childList: true, subtree: true })
    return () => {
      root.removeEventListener('focusin', into)
      root.removeEventListener('focusout', out)
      watch.disconnect()
    }
  }, [rootRef])
}
