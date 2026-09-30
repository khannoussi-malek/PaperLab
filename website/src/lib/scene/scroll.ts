// Where the reader is in the home page's story, as a float index over its sections: 2.4 means 40% of the way from
// section 2 to section 3. Pure maths, no Three.js, so it is unit-tested (tests/scene.test.mjs).

/** The float index of `viewportCenter` among the sections' centres (page px, in page order). */
export function sceneIndex(centers: number[], viewportCenter: number) {
  if (centers.length < 2 || viewportCenter <= centers[0]) return 0
  for (let i = 0; i < centers.length - 1; i++) {
    const a = centers[i]
    const b = centers[i + 1]
    if (viewportCenter < b) return i + (viewportCenter - a) / (b - a)
  }
  return centers.length - 1
}

/** One value per section, blended linearly at the float `index` (clamped to the ends). */
export function blendAt(values: number[], index: number) {
  const last = values.length - 1
  const at = Math.min(Math.max(index, 0), last)
  const i = Math.floor(at)
  const j = Math.min(i + 1, last)
  return values[i] + (values[j] - values[i]) * (at - i)
}

const REST = 3 // px: closer than this to a stop counts as resting on it

const MOVE_ON = 1 / 3 // how far toward the next stop a scroll must get before the page moves on to it

/**
 * Where the page should glide once a scroll stops at `y` (moving in `dir`: 1 down, -1 up), or null to leave it.
 * Past a third of the way to the next stop it moves on to that one; a smaller nudge glides back to the stop it
 * left. `stops` are scroll positions (ascending) where a section sits just right; `free` are [top, bottom] ranges
 * inside sections taller than the screen, where the reader scrolls freely.
 */
export function settleTarget(stops: number[], free: [number, number][], y: number, dir: number): number | null {
  if (!stops.length || stops.some((s) => Math.abs(s - y) < REST)) return null
  if (free.some(([a, b]) => y > a && y < b)) return null
  const above = [...stops].reverse().find((s) => s < y)
  const below = stops.find((s) => s > y)
  if (above === undefined) return below!
  if (below === undefined) return above
  const [left, ahead] = dir > 0 ? [above, below] : [below, above]
  return Math.abs(y - left) / Math.abs(ahead - left) >= MOVE_ON ? ahead : left
}
