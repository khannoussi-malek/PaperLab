import { describe, expect, it } from 'vitest'
import { readToastShape, shapeDistance, toastLensPixels, type ToastShape } from './toastLens'

// A top-right toast: a 120 px pill flush right over a 350 x 52 body (Sileo's pill is 40 px tall).
const expanded: ToastShape = { width: 350, height: 92, pillX: 230, pillWidth: 120 }
const collapsed: ToastShape = { ...expanded, height: 40 }

const pixel = (shape: ToastShape, x: number, y: number) => {
  const data = toastLensPixels(shape)
  const i = (y * shape.width + x) * 4
  return { push: { x: data[i] - 128, y: data[i + 2] - 128 }, edge: data[i + 1] }
}

describe('shapeDistance', () => {
  it('is negative inside the glass and positive outside it', () => {
    expect(shapeDistance(expanded, 175, 70)).toBeLessThan(0)
    expect(shapeDistance(expanded, 290, 20)).toBeLessThan(0)
    // Left of the pill, above the body: the empty corner of the toast box.
    expect(shapeDistance(expanded, 60, 15)).toBeGreaterThan(0)
  })

  it('joins pill and body with a smooth fillet, like Sileo\'s blob, not a square inner corner', () => {
    // Just left of the pill, just above the body: inside the blend, outside both rounded rects.
    expect(shapeDistance(expanded, 228, 38)).toBeLessThan(0)
  })

  it('is only the pill while the toast is collapsed', () => {
    expect(shapeDistance(collapsed, 175, 70)).toBeGreaterThan(0)
    expect(shapeDistance(collapsed, 290, 20)).toBeLessThan(0)
  })
})

describe('toastLensPixels', () => {
  it('leaves the middle of the glass unbent, so the text sits over a calm, frosted centre', () => {
    expect(pixel(expanded, 175, 70)).toEqual({ push: { x: 0, y: 0 }, edge: 0 })
  })

  it('bends along the real outline, drawing from inside the glass (a magnifying rim), strongest at the edge', () => {
    // Inwards, so the rim never samples beyond the toast's box, where the backdrop has nothing to show.
    expect(pixel(expanded, 1, 70).push.x).toBeGreaterThan(60)
    expect(pixel(expanded, 175, 90).push.y).toBeLessThan(-60)
  })

  it('bends at the pill\'s own left edge too, inside the toast box, which a stretched square map never did', () => {
    const atPillEdge = pixel(expanded, 231, 20)
    expect(atPillEdge.push.x).toBeGreaterThan(40)
    expect(atPillEdge.edge).toBeGreaterThan(100)
  })

  it('fades the bend out over the band: weaker a few pixels in than at the very edge', () => {
    expect(Math.abs(pixel(expanded, 6, 70).push.x)).toBeLessThan(Math.abs(pixel(expanded, 1, 70).push.x))
  })

  it('keeps only a thin rim crisp, so even the 40 px pill has a frosted middle behind its title', () => {
    expect(pixel(expanded, 290, 20).edge).toBe(0)
    expect(pixel(expanded, 290, 9).edge).toBe(0)
  })

  it('leaves everything outside the glass alone', () => {
    expect(pixel(expanded, 60, 15)).toEqual({ push: { x: 0, y: 0 }, edge: 0 })
  })
})

describe('readToastShape', () => {
  it('reads Sileo\'s size variables off the toast element', () => {
    const toast = { offsetWidth: 350, style: { getPropertyValue: (name: string) => ({ '--_h': '92px', '--_px': '230px', '--_pw': '120px' })[name] ?? '' } }
    expect(readToastShape(toast)).toEqual(expanded)
  })

  it('gives up on a toast that has not been laid out yet', () => {
    const toast = { offsetWidth: 0, style: { getPropertyValue: () => '' } }
    expect(readToastShape(toast)).toBeNull()
  })
})
