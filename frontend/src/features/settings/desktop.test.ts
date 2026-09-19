import { describe, expect, it } from 'vitest'
import { desktopBridge, type PaperlabDesktop } from './desktop'

const bridge: PaperlabDesktop = {
  getKeepRunning: async () => false,
  setKeepRunning: async () => {},
  getUpdatesEnabled: async () => true,
  setUpdatesEnabled: async () => {},
}

// useDesktop() is desktopBridge(globalThis). It isn't called here: oxlint's react/rules-of-hooks refuses a use… call
// outside a component.
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
})
