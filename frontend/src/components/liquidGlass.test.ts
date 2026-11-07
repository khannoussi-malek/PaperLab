import { describe, expect, it } from 'vitest'
import { bendsLight, lensPixels } from './liquidGlass'

const at = (pixels: Uint8ClampedArray, size: number, x: number, y: number) => {
  const i = (y * size + x) * 4
  return { r: pixels[i], g: pixels[i + 1], b: pixels[i + 2], a: pixels[i + 3] }
}

describe('lensPixels', () => {
  const size = 64
  const pixels = lensPixels(size, 0.25)

  it('is one opaque RGBA pixel per cell', () => {
    expect(pixels).toHaveLength(size * size * 4)
    expect(at(pixels, size, 10, 50).a).toBe(255)
  })

  it('leaves the middle neutral (128), so the centre of the glass shows the page unbent', () => {
    expect(at(pixels, size, 32, 32)).toMatchObject({ r: 128, g: 128, b: 128 })
  })

  it('bends hardest at the edges: red follows x, blue follows y, both away from 128', () => {
    expect(at(pixels, size, 0, 32).r).toBe(1)
    expect(at(pixels, size, size - 1, 32).r).toBe(255)
    expect(at(pixels, size, 32, 0).b).toBe(1)
    expect(at(pixels, size, 32, size - 1).b).toBe(255)
  })

  it('curves like the rim of a lens: gentle at the inner edge of the band, steep at the very edge', () => {
    const r = (x: number) => 128 - at(pixels, size, x, 32).r
    // The band is 16 px wide here; the push grows with the square of the distance into it.
    expect(r(12)).toBeGreaterThan(0)
    expect(r(12)).toBeLessThan(r(8))
    expect(r(8) - r(12)).toBeLessThan(r(0) - r(4))
  })
})

describe('bendsLight', () => {
  it('is true for Chromium, which can run an SVG filter inside backdrop-filter (Chrome, Edge, Electron)', () => {
    expect(bendsLight({ brands: [{ brand: 'Chromium', version: '142' }] }, '')).toBe(true)
  })

  it('is false for Safari and Firefox, which get plain frosted glass instead', () => {
    expect(bendsLight(undefined, 'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15')).toBe(false)
    expect(bendsLight(undefined, 'Mozilla/5.0 (Macintosh; rv:140.0) Gecko/20100101 Firefox/140.0')).toBe(false)
  })

  it('falls back to the user agent when userAgentData is missing', () => {
    expect(bendsLight(undefined, 'Mozilla/5.0 AppleWebKit/537.36 Chrome/142.0 Safari/537.36')).toBe(true)
  })
})
