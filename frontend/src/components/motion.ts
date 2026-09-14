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

/** Small pressable controls shrink slightly while held. The element needs a transition that covers `scale`. */
export const pressable = 'motion-safe:active:scale-[0.97]'

// ponytail: "new" = created in the last few seconds, judged by the browser clock. Fine for a local-first app on one
// machine; track seen ids instead if the API ever runs somewhere with a different clock.
const FRESH_MS = 5000

/** Whether a record was just created, so it animates in once, but not when it is reloaded or re-shown by a filter. */
export function isFresh(createdAt: string, now: number = Date.now()): boolean {
  const created = Date.parse(createdAt)
  return Number.isFinite(created) && now - created < FRESH_MS
}
