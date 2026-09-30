// After a scroll stops, glide to the next section in the direction the reader was going, so every section comes to
// rest centred under the header, where the scene holds its pose exactly. Sections taller than the screen scroll
// freely inside, and the end of the page (the footer) is the last stop. The choice is settleTarget (scroll.ts).
import { settleTarget } from './scroll'

const QUIET = 140 // ms without a scroll event: the reader (or the momentum) has stopped

export function settleScroll(sections: HTMLElement[]) {
  const root = document.documentElement
  let lastY = scrollY
  let dir = 1
  let gliding = false
  let timer = 0

  // Stops in page coordinates, measured now (sections can change size).
  const measure = () => {
    const pad = parseFloat(getComputedStyle(root).scrollPaddingTop) || 0
    const port = innerHeight - pad
    const max = root.scrollHeight - innerHeight
    const clamp = (y: number) => Math.min(max, Math.max(0, y))
    const stops: number[] = [max]
    const free: [number, number][] = []
    for (const el of sections) {
      const r = el.getBoundingClientRect()
      const top = r.top + scrollY
      if (r.height <= port + 1) stops.push(clamp(top + r.height / 2 - (pad + port / 2)))
      else {
        const range: [number, number] = [clamp(top - pad), clamp(top + r.height - innerHeight)]
        stops.push(...range)
        free.push(range)
      }
    }
    return { stops: stops.sort((a, b) => a - b), free }
  }

  const settle = () => {
    if (gliding) {
      gliding = false // our own glide has landed
      return
    }
    const { stops, free } = measure()
    const to = settleTarget(stops, free, scrollY, dir)
    if (to === null) return
    gliding = true
    scrollTo({ top: to, behavior: 'smooth' })
  }
  const onScroll = () => {
    if (!gliding && scrollY !== lastY) dir = scrollY > lastY ? 1 : -1
    lastY = scrollY
    clearTimeout(timer)
    timer = window.setTimeout(settle, QUIET)
  }
  // A wheel, touch or key during a glide hands the page back to the reader.
  const takeOver = () => (gliding = false)
  const events = ['wheel', 'touchstart', 'keydown'] as const
  addEventListener('scroll', onScroll, { passive: true })
  for (const e of events) addEventListener(e, takeOver, { passive: true })
  return () => {
    clearTimeout(timer)
    removeEventListener('scroll', onScroll)
    for (const e of events) removeEventListener(e, takeOver)
  }
}
