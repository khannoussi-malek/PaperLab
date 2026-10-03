// Timing for the app's 3D moments (pure, no three.js): the startup animation's intro, easing, and a sheen that
// crosses every few seconds. Ported from desktop/src/startup-scene.js.

export const clamp01 = (x: number) => (Number.isNaN(x) ? 0 : Math.min(1, Math.max(0, x)))
/** 0 before `at`, 1 after `at + len`, linear between. */
export const progress = (t: number, at: number, len: number) => clamp01((t - at) / len)
/** The app's ease-out. */
export const out = (x: number) => 1 - (1 - x) ** 3
export const lerp = (a: number, b: number, u: number) => a + (b - a) * u

/** A seeded random, so every visit draws the same scene. */
export function seeded(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
}

/** Moves `current` toward `target` by the same share per second at any frame rate; a held target holds. */
export const approach = (current: number, target: number, dt: number, rate = 3) =>
  current + (target - current) * (1 - Math.exp(-rate * dt))

/** A light crossing a page once every `every` seconds: 0 off its left edge, 1 off its right. */
export const sheenEvery = (t: number, every = 6, len = 1.4) => progress(t % every, every - len, len)

export type Intro = { gather: number; card: number; sweep: number; flash: number; swarm: number; sheen: number }

/** By this many seconds the intro is fully formed. */
export const INTRO_FORMED = 4

/** The intro's clock → how far each part has got (0..1). */
export function intro(u: number): Intro {
  return {
    gather: out(progress(u, 0.6, 1.6)), // dust flies into the mark's outline
    card: out(progress(u, 1.7, 0.6)), // the white logo card fades in over the dust
    sweep: out(progress(u, 2.3, 0.7)), // the highlighter crosses the line
    flash: Math.sin(Math.PI * progress(u, 2.9, 0.7)), // the line's glow as it lands
    swarm: lerp(1, 0.75, progress(u, 2.2, 1.4)), // flying pages calm down behind the mark
    sheen: progress(u, 2.7, 1.2), // a light crossing the page as the highlighter lands
  }
}
