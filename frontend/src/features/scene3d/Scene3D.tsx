import { useEffect, useRef, useState, type ReactNode } from 'react'
import { hasWebGL } from '@/features/graph/viewModel'
import { useBoxSize } from '@/features/graph/useBoxSize'
import { useChartTheme } from '@/features/charts/useChartTheme'
import { cn } from '@/lib/utils'

// One of the app's 3D moments: decoration only (the canvas is aria-hidden; every word stays in the page). Runs only
// with WebGL and motion allowed; three.js arrives with the director, the first time a scene is shown.

export type Running<I> = {
  resize(width: number, height: number): void
  /** `t`: seconds the scene has run (paused time not counted); `dt`: this step, at most MAX_DT. */
  frame(t: number, dt: number, input: I): void
  refog(): void
  dispose(): void
}
export type Director<I> = (canvas: HTMLCanvasElement) => Running<I>

/** The longest step a frame takes, so a return from a hidden tab never jumps the scene ahead. */
export const MAX_DT = 0.1

let webgl: boolean | undefined
const allowed = () => (webgl ??= hasWebGL()) && !matchMedia('(prefers-reduced-motion: reduce)').matches

type Props<I> = {
  load: () => Promise<{ default: Director<I> }>
  input: I
  /** Shown instead of the scene when it can't run, and until it starts. */
  fallback?: ReactNode
  className?: string
  /** For tests: whether a scene may run here (WebGL, motion). */
  canDraw?: () => boolean
}

export function Scene3D<I>({ load, input, fallback = null, className, canDraw = allowed }: Props<I>) {
  const [ok] = useState(canDraw)
  const [live, setLive] = useState(false)
  const theme = useChartTheme()
  const [box, size] = useBoxSize<HTMLDivElement>()
  const canvas = useRef<HTMLCanvasElement>(null)
  const running = useRef<Running<I> | null>(null)
  // Read every frame, so a new input never restarts the scene.
  const latest = useRef(input)
  useEffect(() => {
    latest.current = input
  })

  useEffect(() => {
    if (!ok || !canvas.current) return
    const element = canvas.current
    let stopped = false
    let raf = 0
    let last: number | null = null
    let t = 0
    let visible = true
    const step = (now: number) => {
      raf = requestAnimationFrame(step)
      if (!visible || document.hidden) return void (last = null)
      const dt = last === null ? 0 : Math.min((now - last) / 1000, MAX_DT)
      last = now
      t += dt
      running.current?.frame(t, dt, latest.current)
    }
    const seen = typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver(([entry]) => void (visible = entry.isIntersecting))
    seen?.observe(element)
    load()
      .then(({ default: director }) => {
        if (stopped) return
        running.current = director(element)
        setLive(true)
        raf = requestAnimationFrame(step)
      })
      .catch(() => undefined) // ponytail: decoration only; the fallback stays and nothing is logged, as in Graph3DView
    return () => {
      stopped = true
      cancelAnimationFrame(raf)
      seen?.disconnect()
      running.current?.dispose()
      running.current = null
    }
  }, [ok, load])

  // The app's own Light/Dark/System toggle sets a class on <html>; the scene's fog follows it.
  useEffect(() => {
    running.current?.refog()
  }, [theme, live])

  useEffect(() => {
    if (size.width > 0) running.current?.resize(size.width, size.height)
  }, [size, live])

  if (!ok) return <>{fallback}</>
  return (
    <div ref={box} className={cn('relative', className)}>
      {!live && fallback}
      <canvas ref={canvas} aria-hidden="true" className={cn('absolute inset-0 size-full', !live && 'invisible')} />
    </div>
  )
}
