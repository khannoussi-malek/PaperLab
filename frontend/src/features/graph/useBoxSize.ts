import { useEffect, useRef, useState } from 'react'

/** A box's size in whole pixels, following it as it resizes: canvases and SVGs need pixel sizes, not CSS ones. */
export function useBoxSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width: Math.round(width), height: Math.round(height) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, size] as const
}
