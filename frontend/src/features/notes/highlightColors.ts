export type ColorChoice = { name: string; hex: string }
export type ColorStorage = Pick<Storage, 'getItem' | 'setItem'>

export const DEFAULT_COLOR = '#facc15'

// Violet is left out on purpose: in this UI it means "written by AI".
export const PRESET_COLORS: ColorChoice[] = [
  { name: 'Yellow', hex: '#facc15' },
  { name: 'Green', hex: '#4ade80' },
  { name: 'Blue', hex: '#60a5fa' },
  { name: 'Pink', hex: '#f472b6' },
  { name: 'Orange', hex: '#fb923c' },
]

const HEX_COLOR = /^#[0-9a-f]{6}$/i
const FILL_ALPHA = 0.4
const STORAGE_KEY = 'paperlab-highlight-color'

export const isHexColor = (value: unknown): value is string => typeof value === 'string' && HEX_COLOR.test(value)

/** A highlight's fill: the note colour at 40%, drawn with mix-blend-multiply so the text stays readable. */
export function highlightFill(hex: string): string {
  const color = isHexColor(hex) ? hex : DEFAULT_COLOR
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${FILL_ALPHA})`
}

/** `window.localStorage`, or undefined where even reading it throws (sandboxed or blocked storage). */
export function browserStorage(): ColorStorage | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined
  }
}

/** The colour new highlights start on. */
export function loadLastColor(storage: ColorStorage | undefined): string {
  try {
    const stored = storage?.getItem(STORAGE_KEY)
    return isHexColor(stored) ? stored.toLowerCase() : DEFAULT_COLOR
  } catch {
    return DEFAULT_COLOR
  }
}

export function saveLastColor(storage: ColorStorage | undefined, hex: string): void {
  try {
    storage?.setItem(STORAGE_KEY, hex)
  } catch {
    // ponytail: blocked storage only loses the "remember the last colour" convenience.
  }
}
