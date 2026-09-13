import { describe, expect, it } from 'vitest'
import { DEFAULT_COLOR, PRESET_COLORS, highlightFill, isHexColor, loadLastColor, saveLastColor } from './highlightColors'

const memoryStorage = (initial: Record<string, string> = {}) => {
  const data = new Map(Object.entries(initial))
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => void data.set(key, value) }
}

const blockedStorage = {
  getItem: (): string | null => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('highlightFill', () => {
  it('draws the note colour at 40%', () => {
    expect(highlightFill('#4ade80')).toBe('rgba(74, 222, 128, 0.4)')
  })

  it('falls back to yellow for a malformed colour', () => {
    expect(highlightFill('green')).toBe(highlightFill(DEFAULT_COLOR))
  })
})

describe('isHexColor', () => {
  it('accepts #rrggbb in either case and nothing else', () => {
    expect(['#facc15', '#FACC15'].map((v) => isHexColor(v))).toEqual([true, true])
    expect(['facc15', '#fff', '#facc1g', null].map((v) => isHexColor(v))).toEqual([false, false, false, false])
  })
})

describe('last used colour', () => {
  it('round-trips through storage and starts the presets on yellow', () => {
    const storage = memoryStorage()
    saveLastColor(storage, '#f472b6')
    expect(loadLastColor(storage)).toBe('#f472b6')
    expect(PRESET_COLORS[0].hex).toBe(DEFAULT_COLOR)
  })

  it('starts on yellow when storage is missing, blocked or holds junk', () => {
    expect(loadLastColor(undefined)).toBe(DEFAULT_COLOR)
    expect(loadLastColor(blockedStorage)).toBe(DEFAULT_COLOR)
    expect(loadLastColor(memoryStorage({ 'paperlab-highlight-color': 'purple' }))).toBe(DEFAULT_COLOR)
  })

  it('never throws when storage is blocked', () => {
    expect(() => saveLastColor(blockedStorage, '#4ade80')).not.toThrow()
  })
})
