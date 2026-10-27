import { useEffect } from 'react'

/** While `active`, the browser asks before the tab is closed or reloaded (its own prompt, not a dialog of ours). */
export function useLeaveWarning(active: boolean) {
  useEffect(() => {
    if (!active) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [active])
}
