import { useLayoutEffect, useRef } from "react"

/**
 * The glass highlight that glides between a menu's items (dropdown and context menus, their submenus, selects; see
 * "Glass" in design-system/MASTER.md). Put it first inside the positioned element that holds the items: it follows
 * whichever item Radix marks `data-highlighted` (pointer or keyboard), fades out when none is, and fades back in at
 * the next one rather than sliding from where it last was. Items paint no highlight of their own.
 */
export function MenuGlide() {
  const ref = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const pill = ref.current
    const menu = pill?.parentElement
    if (!pill || !menu) return
    const place = () => {
      const item = menu.querySelector<HTMLElement>("[data-highlighted]")
      if (!item) {
        pill.dataset.hidden = ""
        return
      }
      const reappearing = "hidden" in pill.dataset
      if (reappearing) delete pill.dataset.ready
      pill.style.transform = `translate(${item.offsetLeft}px, ${item.offsetTop}px)`
      pill.style.width = `${item.offsetWidth}px`
      pill.style.height = `${item.offsetHeight}px`
      delete pill.dataset.hidden
      // Glide from item to item; after a gap, appear in place first and glide from the next move on.
      if (reappearing) requestAnimationFrame(() => (pill.dataset.ready = ""))
      else pill.dataset.ready = ""
    }
    place()
    const watch = new MutationObserver(place)
    watch.observe(menu, { subtree: true, attributes: true, attributeFilter: ["data-highlighted"] })
    return () => watch.disconnect()
  }, [])
  return (
    <span
      ref={ref}
      aria-hidden="true"
      data-menu-glide
      data-hidden=""
      className="pointer-events-none absolute top-0 left-0 rounded-md will-change-transform bg-accent shadow-xs ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] data-hidden:opacity-0 motion-safe:transition-opacity motion-safe:duration-150 motion-safe:data-ready:transition-[transform,width,height,opacity] motion-safe:data-ready:duration-220 motion-safe:data-ready:ease-[cubic-bezier(0.34,1.3,0.64,1)]"
    />
  )
}
