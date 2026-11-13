/** What the desktop app's preload script puts on PaperLab's window (desktop/src/preload.ts). Absent in a browser. */
export type PaperlabDesktop = {
  getKeepRunning(): Promise<boolean>
  setKeepRunning(value: boolean): Promise<void>
  getUpdatesEnabled(): Promise<boolean>
  setUpdatesEnabled(value: boolean): Promise<void>
}

const BRIDGE_METHODS = ['getKeepRunning', 'setKeepRunning', 'getUpdatesEnabled', 'setUpdatesEnabled'] as const

/** The bridge on `scope` (a page's window is its globalThis), or null in a normal browser and in Node, and null for
 * a partial bridge too (a stale or broken preload), so callers never meet a bridge missing one of its methods. */
export function desktopBridge(scope: object): PaperlabDesktop | null {
  const candidate = (scope as { paperlabDesktop?: Partial<PaperlabDesktop> }).paperlabDesktop
  const isComplete = candidate !== undefined && BRIDGE_METHODS.every((method) => typeof candidate[method] === 'function')
  return isComplete ? (candidate as PaperlabDesktop) : null
}

/** The desktop app's bridge, or null in a normal browser: it gates Settings' Desktop app section and Connect Claude's
 * line. It never changes while the page lives, so it needs no state. */
export function useDesktop(): PaperlabDesktop | null {
  return desktopBridge(globalThis)
}

/** The voice methods the desktop app's preload adds to the same bridge (desktop/src/preload.ts). An app older than voice
 * has the four methods of PaperlabDesktop and none of these, so Settings falls back to the compose-flag instructions. */
export type VoiceBridge = {
  getVoiceEnabled(): Promise<boolean>
  setVoiceEnabled(value: boolean): Promise<{ ok: boolean; detail: string | null }>
  /** Each progress line of turning voice on; the returned function stops listening. */
  onVoiceProgress(callback: (line: string) => void): () => void
  removeVoiceModels(): Promise<{ ok: boolean; detail: string | null }>
  voiceOutOfMemory(): Promise<boolean>
}

const VOICE_METHODS = ['getVoiceEnabled', 'setVoiceEnabled', 'onVoiceProgress', 'removeVoiceModels', 'voiceOutOfMemory'] as const

/** The voice bridge on `scope`, or null when any of its five methods is missing (an older desktop app, or a browser). */
export function voiceBridge(scope: object): VoiceBridge | null {
  const candidate = (scope as { paperlabDesktop?: Partial<VoiceBridge> }).paperlabDesktop
  const isComplete = candidate !== undefined && VOICE_METHODS.every((method) => typeof candidate[method] === 'function')
  return isComplete ? (candidate as VoiceBridge) : null
}

/** The voice bridge for this page, or null. Like useDesktop, it never changes while the page lives. */
export function useVoiceBridge(): VoiceBridge | null {
  return voiceBridge(globalThis)
}
