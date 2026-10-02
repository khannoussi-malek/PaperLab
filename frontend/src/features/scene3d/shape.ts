// The PaperLab mark as points (pure): a page outline and four text lines, centred, in world units.

/** The logo card's size: the mark's 640 × 840 page. */
export const MARK = { w: 2.4, h: 2.4 * (840 / 640) }
/** The highlighted line's height on the card (line 4 of the painted page). */
export const BAND_Y = (0.5 - (190 + 4 * 52 + 9) / 840) * MARK.h

export type Point = readonly [number, number, number]

export function markPoints(n: number, rand: () => number): Point[] {
  const { w, h } = MARK
  return Array.from({ length: n }, (): Point => {
    let x: number
    let y: number
    if (rand() < 0.55) {
      const e = rand() * 2 * (w + h)
      if (e < w) [x, y] = [e - w / 2, h / 2]
      else if (e < w + h) [x, y] = [w / 2, h / 2 - (e - w)]
      else if (e < 2 * w + h) [x, y] = [w / 2 - (e - w - h), -h / 2]
      else [x, y] = [-w / 2, -h / 2 + (e - 2 * w - h)]
    } else {
      const line = Math.floor(rand() * 4)
      x = -w * 0.35 + rand() * w * (line === 3 ? 0.4 : 0.7)
      y = h * (0.28 - line * 0.19)
    }
    return [x, y, (rand() - 0.5) * 0.08]
  })
}
