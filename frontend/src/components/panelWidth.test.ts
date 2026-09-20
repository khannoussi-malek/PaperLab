import { describe, expect, it } from 'vitest'
import { clampPanelWidth, loadPanelWidth, maxPanelWidth, savePanelWidth, type PanelLimits } from './panelWidth'

const PANEL: PanelLimits = { storageKey: 'test-panel-width', defaultWidth: 360, minWidth: 320, maxShare: 0.6 }
const NARROW: PanelLimits = { storageKey: 'other-panel-width', defaultWidth: 420, minWidth: 280, maxShare: 0.5 }

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
  it('is the panel’s share of the window, but never below its minimum', () => {
    expect(maxPanelWidth(PANEL, 1400)).toBe(840)
    expect(maxPanelWidth(PANEL, 400)).toBe(PANEL.minWidth)
  })

  it('reads each panel’s own share', () => {
    expect(maxPanelWidth(NARROW, 1400)).toBe(700)
  })
})

describe('clampPanelWidth', () => {
  it('keeps a width between the minimum and the share, in whole pixels', () => {
    expect(clampPanelWidth(PANEL, 500.4, 1400)).toBe(500)
    expect(clampPanelWidth(PANEL, 10, 1400)).toBe(PANEL.minWidth)
    expect(clampPanelWidth(PANEL, 5000, 1400)).toBe(840)
  })

  it('falls back to that panel’s default for a width that is not a number', () => {
    expect(clampPanelWidth(PANEL, Number.NaN, 1400)).toBe(360)
    expect(clampPanelWidth(NARROW, Number.NaN, 1400)).toBe(420)
  })
})

describe('loadPanelWidth / savePanelWidth', () => {
  it('round-trips a saved width', () => {
    const storage = memoryStorage()
    savePanelWidth(PANEL, storage, 520)
    expect(loadPanelWidth(PANEL, storage)).toBe(520)
  })

  it('keeps each panel’s width under its own key, so one does not move the other', () => {
    const storage = memoryStorage()
    savePanelWidth(PANEL, storage, 520)
    savePanelWidth(NARROW, storage, 600)
    expect(loadPanelWidth(PANEL, storage)).toBe(520)
    expect(loadPanelWidth(NARROW, storage)).toBe(600)
  })

  it('starts at the default when nothing usable is stored', () => {
    expect(loadPanelWidth(PANEL, memoryStorage())).toBe(360)
    expect(loadPanelWidth(PANEL, memoryStorage({ 'test-panel-width': 'wide' }))).toBe(360)
    expect(loadPanelWidth(PANEL, undefined)).toBe(360)
  })

  it('treats blocked storage as empty, and saving to it does not throw', () => {
    expect(loadPanelWidth(PANEL, blockedStorage)).toBe(360)
    expect(() => savePanelWidth(PANEL, blockedStorage, 400)).not.toThrow()
  })
})
