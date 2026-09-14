import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PANEL_WIDTH,
  MIN_PANEL_WIDTH,
  clampPanelWidth,
  loadPanelWidth,
  maxPanelWidth,
  savePanelWidth,
} from './panelWidth'

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

describe('maxPanelWidth', () => {
  it('is 60% of the window, but never below the minimum', () => {
    expect(maxPanelWidth(1400)).toBe(840)
    expect(maxPanelWidth(400)).toBe(MIN_PANEL_WIDTH)
  })
})

describe('clampPanelWidth', () => {
  it('keeps a width between the minimum and 60% of the window, in whole pixels', () => {
    expect(clampPanelWidth(500.4, 1400)).toBe(500)
    expect(clampPanelWidth(10, 1400)).toBe(MIN_PANEL_WIDTH)
    expect(clampPanelWidth(5000, 1400)).toBe(840)
  })

  it('falls back to the default for a width that is not a number', () => {
    expect(clampPanelWidth(Number.NaN, 1400)).toBe(DEFAULT_PANEL_WIDTH)
  })
})

describe('loadPanelWidth / savePanelWidth', () => {
  it('round-trips a saved width', () => {
    const storage = memoryStorage()
    savePanelWidth(storage, 520)
    expect(loadPanelWidth(storage)).toBe(520)
  })

  it('starts at the default when nothing usable is stored', () => {
    expect(loadPanelWidth(memoryStorage())).toBe(DEFAULT_PANEL_WIDTH)
    expect(loadPanelWidth(memoryStorage({ 'paperlab-panel-width': 'wide' }))).toBe(DEFAULT_PANEL_WIDTH)
    expect(loadPanelWidth(undefined)).toBe(DEFAULT_PANEL_WIDTH)
  })

  it('treats blocked storage as empty, and saving to it does not throw', () => {
    expect(loadPanelWidth(blockedStorage)).toBe(DEFAULT_PANEL_WIDTH)
    expect(() => savePanelWidth(blockedStorage, 400)).not.toThrow()
  })
})
