import { useLayoutEffect, useRef } from 'react'

type Spot = { x: number; y: number; width: number; height: number }

/**
 * Where the sidebar's pill last stood. Every view draws its own sidebar (see `AppShell`), so this memory is what lets
 * the pill glide from the previous page's item instead of simply appearing on the new one.
 */
let last: Spot | null = null

/** Tests start from a sidebar that has never been drawn. */
export const forgetRailPill = () => {
  last = null
}

const same = (a: Spot, b: Spot) => a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height

/** The tabs' glide: 650 ms with a slight springy overshoot (see "Workspaces" in design-system/MASTER.md). */
const GLIDE: KeyframeAnimationOptions = { duration: 650, easing: 'cubic-bezier(0.34, 1.3, 0.64, 1)' }

const translate = (spot: Spot) => `translate(${spot.x}px, ${spot.y}px)`
const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Keeps the sidebar's glass pill (see "Shell" in design-system/MASTER.md) on the current page's item. It measures
 * against the rail, so the scrolling workspace list is handled, follows that list's scroll, and hides while the item is
 * scrolled out of view. On a new page the pill is put on its new item at once and one Web Animation glides it there
 * from where the last page left it: transform only, so it runs on the compositor and a page busy rendering can't stall
 * it, and it starts the moment the new sidebar appears. `activeKey` changes whenever the current item can.
 */
export function useRailPill(activeKey: string) {
  const railRef = useRef<HTMLElement>(null)
  const pillRef = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const rail = railRef.current
    const pill = pillRef.current
    if (!rail || !pill) return
    const measure = (): Spot | null => {
      const item = rail.querySelector<HTMLElement>('a[aria-current="page"]')
      if (!item) return null
      const box = rail.getBoundingClientRect()
      const spot = item.getBoundingClientRect()
      const scroller = item.closest<HTMLElement>('[data-rail-scroll]')?.getBoundingClientRect()
      if (scroller && (spot.bottom <= scroller.top || spot.top >= scroller.bottom)) return null
      return { x: spot.left - box.left, y: spot.top - box.top, width: spot.width, height: spot.height }
    }
    const place = () => {
      const spot = measure()
      if (!spot) {
        pill.dataset.hidden = ''
        return
      }
      delete pill.dataset.hidden
      pill.style.transform = translate(spot)
      pill.style.width = `${spot.width}px`
      pill.style.height = `${spot.height}px`
      last = spot
    }

    const from = last
    place()
    const to = last
    if (from && to && !same(from, to) && typeof pill.animate === 'function' && !reducedMotion()) {
      pill.animate([{ transform: translate(from) }, { transform: translate(to) }], GLIDE)
    }

    rail.addEventListener('scroll', place, true)
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place)
    resize?.observe(rail)
    return () => {
      rail.removeEventListener('scroll', place, true)
      resize?.disconnect()
    }
  }, [activeKey])
  return { railRef, pillRef }
}
