import { describe, expect, it } from 'vitest'
import { bendsLight, lensKey, lensPixels } from './lens'

const at = (w: number, h: number, radius: number, edge: number, x: number, y: number) => {
  const data = lensPixels({ width: w, height: h, radius }, edge)
  const i = (y * w + x) * 4
  return { x: data[i] - 128, y: data[i + 2] - 128 }
}

describe('lensPixels', () => {
  it('leaves the middle of a surface unbent', () => {
    expect(at(200, 100, 12, 16, 100, 50)).toEqual({ x: 0, y: 0 })
  })

  it('pulls the page in from the edge (a magnifying rim), strongest right at it', () => {
    expect(at(200, 100, 12, 16, 0, 50).x).toBeGreaterThan(100)
    expect(at(200, 100, 12, 16, 199, 50).x).toBeLessThan(-100)
    expect(at(200, 100, 12, 16, 100, 99).y).toBeLessThan(-100)
    expect(Math.abs(at(200, 100, 12, 16, 6, 50).x)).toBeLessThan(at(200, 100, 12, 16, 0, 50).x)
  })

  it('bends only as deep as Edge width reaches', () => {
    expect(at(200, 100, 12, 16, 30, 50)).toEqual({ x: 0, y: 0 })
    expect(at(200, 100, 12, 48, 30, 50).x).toBeGreaterThan(0)
  })

  it('follows the rounded corner: the cut-off corner is outside the glass and left alone', () => {
    expect(at(200, 100, 24, 16, 1, 1)).toEqual({ x: 0, y: 0 })
    // Along the corner's arc the push points diagonally inwards.
    const arc = at(200, 100, 24, 16, 8, 8)
    expect(arc.x).toBeGreaterThan(0)
    expect(arc.y).toBeGreaterThan(0)
  })
})

describe('lensKey', () => {
  it('shares one lens between surfaces of the same rounded size, so a list of buttons costs one filter', () => {
    expect(lensKey({ width: 32.4, height: 32, radius: 10 }, 16)).toBe(lensKey({ width: 31.8, height: 32.2, radius: 10 }, 16))
    expect(lensKey({ width: 32, height: 32, radius: 10 }, 16)).not.toBe(lensKey({ width: 32, height: 32, radius: 10 }, 24))
  })
})

describe('bendsLight', () => {
  it('is true for Chromium, which runs an SVG filter inside backdrop-filter (Chrome, Edge, Arc, Electron)', () => {
    expect(bendsLight({ brands: [{ brand: 'Chromium', version: '142' }] }, '')).toBe(true)
    expect(bendsLight(undefined, 'Mozilla/5.0 AppleWebKit/537.36 Chrome/142.0 Safari/537.36')).toBe(true)
  })

  it('is false for Safari and Firefox, which keep plain frosted glass', () => {
    expect(bendsLight(undefined, 'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15')).toBe(false)
    expect(bendsLight(undefined, 'Mozilla/5.0 (Macintosh; rv:140.0) Gecko/20100101 Firefox/140.0')).toBe(false)
  })
})
