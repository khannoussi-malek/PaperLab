import type { CSSProperties } from 'react'

type PageSpec = {
  /** Vertical position within the row, so the 7 pages don't all fly along one line. */
  top: string
  width: number
  height: number
  /** One loop of the flight, as a CSS time: faster pages read as closer to the viewer. */
  dur: string
  /** Rotation on the way in/out (`rotateZ`), sign and magnitude varied per page. */
  tilt: string
  animationDelayMs: number
}

/** 7 pages, each a little different in position, size, speed and tilt so the flight doesn't look mechanical. */
const PAGES: PageSpec[] = [
  { top: '6%', width: 26, height: 34, dur: '3.2s', tilt: '-14deg', animationDelayMs: 0 },
  { top: '20%', width: 20, height: 27, dur: '2.6s', tilt: '9deg', animationDelayMs: 420 },
  { top: '33%', width: 30, height: 38, dur: '3.8s', tilt: '-20deg', animationDelayMs: 900 },
  { top: '47%', width: 22, height: 29, dur: '2.9s', tilt: '16deg', animationDelayMs: 1500 },
  { top: '60%', width: 28, height: 36, dur: '3.4s', tilt: '-11deg', animationDelayMs: 300 },
  { top: '73%', width: 18, height: 24, dur: '2.4s', tilt: '22deg', animationDelayMs: 1100 },
  { top: '86%', width: 24, height: 32, dur: '3.6s', tilt: '-17deg', animationDelayMs: 700 },
]

/** Whether `paper` should show the flying-pages layer behind its Library row. */
export const isEmbedding = (paper: { status: string }): boolean => paper.status === 'embedding'

/**
 * A decorative layer of small pages drifting right-to-left behind a Library row, shown only while its paper's
 * `status === 'embedding'`. `aria-hidden` and `pointer-events-none`: it never competes with the row's real content
 * or its "embedding" status badge, and under `prefers-reduced-motion` it is invisible (see `.embedding-page` in
 * index.css), so the row looks exactly like any other in-progress row.
 */
export function EmbeddingFlight() {
  return (
    <div
      aria-hidden
      className="embedding-flight pointer-events-none absolute inset-0 -z-10 overflow-hidden [container-type:inline-size] [perspective:420px]"
    >
      {PAGES.map((page, index) => (
        <span
          key={index}
          className="embedding-page motion-safe:animate-[embedding-fly_var(--dur)_linear_infinite]"
          style={
            {
              top: page.top,
              width: `${page.width}px`,
              height: `${page.height}px`,
              animationDelay: `${page.animationDelayMs}ms`,
              '--dur': page.dur,
              '--tilt': page.tilt,
            } as CSSProperties
          }
        />
      ))}
    </div>
  )
}
