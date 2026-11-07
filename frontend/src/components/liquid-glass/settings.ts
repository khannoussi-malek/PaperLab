/**
 * Liquid glass settings (Settings → Glass; "Glass" in design-system/MASTER.md).
 *
 * The first four knobs are liquid-glass-react's own (its demo, liquid-glass.maxrovensky.com, has the same sliders),
 * with its defaults and its formulas, so values found on the demo carry over one to one. Edge width and opacity are
 * PaperLab's: how deep from the edge the light bends, and how much paint the glass carries.
 */

export type GlassArea = 'floating' | 'chrome' | 'buttons' | 'reader'

export type GlassSettings = {
  enabled: boolean
  /** How far the edge bends the page, in px at full strength (demo: Displacement Scale). */
  displacementScale: number
  /** Frost (demo: Blur Amount); see `blurPx`. */
  blurAmount: number
  /** Colour richness of what shows through, in % (demo: Saturation). */
  saturation: number
  /** Colour split at the edge (demo: Chromatic Aberration); see `channelScales`. */
  aberrationIntensity: number
  /** How deep from the edge the light bends, in px. */
  edgeWidth: number
  /** How opaque the glass's tint is, 0 (clear) to 1 (solid). */
  opacity: number
  areas: Record<GlassArea, boolean>
}

export const GLASS_AREAS: readonly GlassArea[] = ['floating', 'chrome', 'buttons', 'reader']

type NumericKey = Exclude<keyof GlassSettings, 'enabled' | 'areas'>

/** Each slider's min, max and step. */
export const GLASS_RANGES: Record<NumericKey, { min: number; max: number; step: number }> = {
  displacementScale: { min: 0, max: 200, step: 1 },
  blurAmount: { min: 0, max: 1, step: 0.0125 },
  saturation: { min: 100, max: 300, step: 5 },
  aberrationIntensity: { min: 0, max: 10, step: 0.1 },
  edgeWidth: { min: 4, max: 120, step: 1 },
  opacity: { min: 0, max: 1, step: 0.05 },
}

export const DEFAULT_GLASS: GlassSettings = {
  enabled: true,
  displacementScale: 70,
  blurAmount: 0.0625,
  saturation: 140,
  aberrationIntensity: 2,
  edgeWidth: 16,
  opacity: 0.65,
  areas: { floating: true, chrome: true, buttons: true, reader: true },
}

export const STORAGE_KEY = 'paperlab-glass'

const clamp = (value: unknown, key: NumericKey) => {
  const { min, max } = GLASS_RANGES[key]
  return typeof value === 'number' && Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : DEFAULT_GLASS[key]
}

/** Whatever was stored, as valid settings: unknown or broken values fall back to the defaults. */
export function sanitizeGlass(raw: unknown): GlassSettings {
  const value = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const areas = (value.areas && typeof value.areas === 'object' ? value.areas : {}) as Record<string, unknown>
  const numbers = Object.fromEntries(
    (Object.keys(GLASS_RANGES) as NumericKey[]).map((key) => [key, clamp(value[key], key)]),
  ) as Record<NumericKey, number>
  return {
    ...numbers,
    enabled: typeof value.enabled === 'boolean' ? value.enabled : DEFAULT_GLASS.enabled,
    areas: Object.fromEntries(
      GLASS_AREAS.map((area) => [area, typeof areas[area] === 'boolean' ? areas[area] : DEFAULT_GLASS.areas[area]]),
    ) as Record<GlassArea, boolean>,
  }
}

type Storage = { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void }

/** This browser's settings; the defaults when there are none, or when storage is broken or blocked. */
export function loadGlass(storage: Storage): GlassSettings {
  try {
    const stored = storage.getItem(STORAGE_KEY)
    return sanitizeGlass(stored ? JSON.parse(stored) : null)
  } catch {
    return DEFAULT_GLASS
  }
}

/** Remembers the settings; a refused write (private window, full storage) only means they last this session. */
export function saveGlass(settings: GlassSettings, storage: Storage): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // ponytail: nothing to tell the reader; the sliders still work until the page reloads.
  }
}

/** liquid-glass-react's colour split: green bends 5% and blue 10% further than red per step of aberration. */
export function channelScales(settings: GlassSettings) {
  const { displacementScale: scale, aberrationIntensity: split } = settings
  const round = (n: number) => Math.round(n * 100) / 100
  return { red: round(scale), green: round(scale * (1 + split * 0.05)), blue: round(scale * (1 + split * 0.1)) }
}

/** liquid-glass-react's frost: 4 px, plus 32 px per whole step of Blur Amount. */
export const blurPx = (settings: GlassSettings) => 4 + settings.blurAmount * 32
