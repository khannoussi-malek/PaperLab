import { useEffect, useState, type RefObject } from 'react'

export type DeskLayout = 'wide' | 'tabs' | 'single'

export const deskLayout = (width: number): DeskLayout => (width >= 1100 ? 'wide' : width >= 700 ? 'tabs' : 'single')

/** The desk's width: its own box (ResizeObserver) or, where that is missing, the window's. */
export function useDeskWidth(ref: RefObject<HTMLElement | null>): number {
  const measure = () => ref.current?.clientWidth || window.innerWidth
  const [width, setWidth] = useState(measure)
  useEffect(() => {
    setWidth(measure())
    if (typeof ResizeObserver === 'undefined' || !ref.current) {
      const onResize = () => setWidth(measure())
      window.addEventListener('resize', onResize)
      return () => window.removeEventListener('resize', onResize)
    }
    const observer = new ResizeObserver(() => setWidth(measure()))
    observer.observe(ref.current)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref])
  return width
}
