import { describe, expect, it } from 'vitest'
import { blurPx, channelScales, DEFAULT_GLASS, loadGlass, sanitizeGlass, saveGlass, STORAGE_KEY } from './settings'

const memory = () => {
  const store = new Map<string, string>()
  return { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) }
}

describe('sanitizeGlass', () => {
  it('starts from the owner\'s chosen look, tuned in the Settings preview', () => {
    expect(DEFAULT_GLASS).toMatchObject({
      enabled: true,
      displacementScale: 151,
      blurAmount: 0.55,
      saturation: 105,
      aberrationIntensity: 1.3,
      edgeWidth: 8,
      opacity: 0.15,
    })
  })

  it('falls back to the defaults for anything missing or unreadable', () => {
    expect(sanitizeGlass(null)).toEqual(DEFAULT_GLASS)
    expect(sanitizeGlass('nonsense')).toEqual(DEFAULT_GLASS)
    expect(sanitizeGlass({ saturation: 'loud' })).toEqual(DEFAULT_GLASS)
  })

  it('keeps every value inside its slider\'s range', () => {
    const wild = sanitizeGlass({ displacementScale: 9000, blurAmount: -3, saturation: 20, aberrationIntensity: 99, edgeWidth: 0, opacity: 4 })
    expect(wild).toMatchObject({ displacementScale: 200, blurAmount: 0, saturation: 100, aberrationIntensity: 10, edgeWidth: 4, opacity: 1 })
  })

  it('keeps the on/off switches, per area, and ignores unknown areas', () => {
    const settings = sanitizeGlass({ enabled: false, areas: { buttons: false, sidebar: true } })
    expect(settings.enabled).toBe(false)
    expect(settings.areas).toEqual({ ...DEFAULT_GLASS.areas, buttons: false })
  })
})

describe('loadGlass and saveGlass', () => {
  it('remembers the settings in this browser', () => {
    const storage = memory()
    saveGlass({ ...DEFAULT_GLASS, saturation: 200 }, storage)
    expect(storage.getItem(STORAGE_KEY)).toContain('"saturation":200')
    expect(loadGlass(storage).saturation).toBe(200)
  })

  it('survives broken JSON and a storage that refuses access', () => {
    const storage = memory()
    storage.setItem(STORAGE_KEY, '{oops')
    expect(loadGlass(storage)).toEqual(DEFAULT_GLASS)
    const refusing = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
    expect(loadGlass(refusing)).toEqual(DEFAULT_GLASS)
    expect(() => saveGlass(DEFAULT_GLASS, refusing)).not.toThrow()
  })
})

describe('the demo\'s formulas', () => {
  it('splits colour like liquid-glass-react: green and blue bend 5% and 10% more per step of aberration', () => {
    expect(channelScales({ ...DEFAULT_GLASS, displacementScale: 100, aberrationIntensity: 2 })).toEqual({ red: 100, green: 110, blue: 120 })
    expect(channelScales({ ...DEFAULT_GLASS, displacementScale: 100, aberrationIntensity: 0 })).toEqual({ red: 100, green: 100, blue: 100 })
  })

  it('turns Blur Amount into pixels the way the demo does: 4 px plus 32 px per whole step', () => {
    expect(blurPx({ ...DEFAULT_GLASS, blurAmount: 0.5 })).toBe(20)
    expect(blurPx({ ...DEFAULT_GLASS, blurAmount: 0 })).toBe(4)
  })
})
