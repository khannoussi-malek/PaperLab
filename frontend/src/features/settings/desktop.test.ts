import { describe, expect, it } from 'vitest'
import { desktopBridge, voiceBridge, type PaperlabDesktop, type VoiceBridge } from './desktop'

const bridge: PaperlabDesktop = {
  getKeepRunning: async () => false,
  setKeepRunning: async () => {},
  getUpdatesEnabled: async () => true,
  setUpdatesEnabled: async () => {},
}

const voice: VoiceBridge = {
  getVoiceEnabled: async () => false,
  setVoiceEnabled: async () => ({ ok: true, detail: null }),
  onVoiceProgress: () => () => {},
  removeVoiceModels: async () => ({ ok: true, detail: null }),
  voiceOutOfMemory: async () => false,
}

// useDesktop() and useVoiceBridge() are desktopBridge(globalThis) and voiceBridge(globalThis). They aren't called
// here: oxlint's react/rules-of-hooks refuses a use… call outside a component.
describe('desktopBridge', () => {
  it('is absent in a normal browser, which has no bridge on its window', () => {
    expect(desktopBridge({})).toBeNull()
    expect(desktopBridge(globalThis)).toBeNull() // Node, like a browser without the app
  })

  it("is the desktop app's bridge once its preload has put one on the window", () => {
    expect(desktopBridge({ paperlabDesktop: bridge })).toBe(bridge)
  })

  it('is null for a partial bridge (a stale or broken preload), even though something is on the window', () => {
    expect(desktopBridge({ paperlabDesktop: { getKeepRunning: bridge.getKeepRunning } })).toBeNull()
  })

  it('old_bridge_keeps_desktop_section: a bridge with only the four old methods is still the desktop bridge, with no voice bridge', () => {
    const scope = { paperlabDesktop: bridge }
    expect(desktopBridge(scope)).toBe(bridge)
    expect(voiceBridge(scope)).toBeNull()
  })
})

describe('voiceBridge', () => {
  it('is null in a normal browser', () => {
    expect(voiceBridge({})).toBeNull()
  })

  it('is the bridge once all five voice methods are on the window beside the old ones', () => {
    const full = { ...bridge, ...voice }
    expect(voiceBridge({ paperlabDesktop: full })).toBe(full)
  })

  it('is null when any one of the five voice methods is missing', () => {
    const { voiceOutOfMemory: _missing, ...partial } = voice
    expect(voiceBridge({ paperlabDesktop: { ...bridge, ...partial } })).toBeNull()
  })
})
