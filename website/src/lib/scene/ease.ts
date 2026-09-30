// Small timing helpers shared by the scene's parts (pure, no Three.js).
export const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
/** 0 before `at`, 1 after `at + len`, linear between. */
export const progress = (t: number, at: number, len: number) => clamp01((t - at) / len)
/** The app's ease-out. */
export const out = (x: number) => 1 - (1 - x) ** 3
export const lerp = (a: number, b: number, u: number) => a + (b - a) * u
/** A seeded random, so every visit draws the same scene. */
export function seeded(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
}
