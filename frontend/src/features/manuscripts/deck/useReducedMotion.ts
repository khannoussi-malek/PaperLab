import { useEffect, useState } from 'react'

const REDUCED = '(prefers-reduced-motion: reduce)'

/** Follows the OS setting, also while the deck is open. */
export function useReducedMotion(): boolean {
  const [still, setStill] = useState(() => typeof matchMedia === 'function' && matchMedia(REDUCED).matches)
  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const mq = matchMedia(REDUCED)
    const onChange = () => setStill(mq.matches)
    onChange()
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])
  return still
}
