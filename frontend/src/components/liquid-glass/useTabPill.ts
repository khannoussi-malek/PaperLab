import { useLayoutEffect, useRef } from 'react'

/**
 * Keeps the active tab in view and the glass pill (`thumb`) on it: placed before the first paint, then moved on every
 * tab change and whenever the tab's size changes (a count arriving, a font loading). It writes the pill's style
 * directly, so a move costs no React render; the pill's own CSS transition does the sliding. Used by the workspace
 * tabs and the Settings → Glass preview (see "Workspaces" in design-system/MASTER.md).
 */
export function useTabPill(active: string) {
  const list = useRef<HTMLDivElement>(null)
  const thumb = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const tab = list.current?.querySelector<HTMLElement>('[data-state="active"]')
    const pill = thumb.current
    if (!tab || !pill || !list.current) return
    // On a narrow screen the list scrolls sideways: bring the chosen tab into view.
    tab.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
    const place = () => {
      pill.style.transform = `translate(${tab.offsetLeft}px, ${tab.offsetTop}px)`
      pill.style.width = `${tab.offsetWidth}px`
      pill.style.height = `${tab.offsetHeight}px`
      // From now on moves animate; the first placement above happened before the first paint, so it doesn't.
      pill.dataset.ready = ''
    }
    place()
    // ponytail: every browser has ResizeObserver; only bare test environments lack it, and there one placement does.
    if (typeof ResizeObserver === 'undefined') return
    const resize = new ResizeObserver(place)
    resize.observe(tab)
    resize.observe(list.current)
    return () => resize.disconnect()
  }, [active])
  return { listRef: list, thumbRef: thumb }
}

/**
 * A tab bar for the pill: tinted glass with a lit edge, but no blur of its own. A blurring bar would be a backdrop
 * root, and the lens pill inside it would then see only the bar, not the labels behind.
 */
export const PILL_LIST = 'relative bg-glass ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)]'

/** On each tab: the active tab's own fill and shadow are off, since the gliding pill is its background. */
export const PILL_TAB =
  'data-active:bg-transparent data-active:shadow-none group-data-[variant=default]/tabs-list:data-active:shadow-none dark:data-active:border-transparent dark:data-active:bg-transparent'
