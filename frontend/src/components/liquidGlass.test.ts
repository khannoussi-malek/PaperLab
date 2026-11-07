import { describe, expect, it } from 'vitest'
import { bendsLight } from './liquidGlass'

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
