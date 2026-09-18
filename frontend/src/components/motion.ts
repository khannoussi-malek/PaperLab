import { flushSync } from 'react-dom'

/**
 * Motion tokens (see "Motion" in design-system/MASTER.md). Entrances only, opacity and transform only, and every
 * one is `motion-safe`: with the OS set to reduce motion nothing moves. Pair `popIn` with an `origin-*` class so it
 * grows from where it comes from.
 */

/** Pop-ups (hover card, Save as note, note composer): fade in and grow from 95%. */
export const popIn = 'motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-95 motion-safe:duration-200 motion-safe:ease-out'

/** A new item in a list (a note card, a chat Q&A): fade up once, when it is added. */
export const slideUpIn =
  'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-300 motion-safe:ease-out'

/** Pages and tab panels. A panel hidden with `display: none` replays it each time it is shown. */
export const fadeIn = 'motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300 motion-safe:ease-out'

/**
 * A loading placeholder: hidden for its first 150 ms, then fades in. A fast load (most of this local app) never flashes
 * it; a slow one still says it is working. Put it on the element only while it shows the placeholder.
 */
export const delayedIn =
  'motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200 motion-safe:delay-150 motion-safe:fill-mode-backwards'

/** Small pressable controls shrink slightly while held. The element needs a transition that covers `scale`. */
export const pressable = 'motion-safe:active:scale-[0.97]'

/**
 * Runs an update that changes the whole view (a page, a theme) as a view transition: the browser cross-fades the old
 * view into the new one instead of swapping it in a frame. With reduced motion, or in a browser without the API, the
 * update just runs. `flushSync` puts React's render inside the transition, so the new view is what it fades to.
 */
export function withViewTransition(update: () => void) {
  if (typeof document.startViewTransition !== 'function' || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    update()
    return
  }
  document.startViewTransition(() => flushSync(update))
}

// ponytail: "new" = created in the last few seconds, judged by the browser clock. Fine for a local-first app on one
// machine; track seen ids instead if the API ever runs somewhere with a different clock.
const FRESH_MS = 5000

/** Whether a record was just created, so it animates in once, but not when it is reloaded or re-shown by a filter. */
export function isFresh(createdAt: string, now: number = Date.now()): boolean {
  const created = Date.parse(createdAt)
  return Number.isFinite(created) && now - created < FRESH_MS
}
